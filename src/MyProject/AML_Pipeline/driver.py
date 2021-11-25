import argparse
import logging
import os

from azureml.core import Experiment, Run, Workspace, VERSION
from azureml.core.compute import ComputeTarget, AmlCompute
from azureml.core.compute_target import ComputeTargetException
from azureml.core.conda_dependencies import CondaDependencies
from azureml.data.data_reference import DataReference
from azureml.core.runconfig import RunConfiguration, DEFAULT_CPU_IMAGE
from azureml.pipeline.core import (
    Pipeline,
    PipelineData,
    PipelineParameter,
    PublishedPipeline,
)
from azureml.pipeline.steps import PythonScriptStep

from ischia.core.config import Config
from ischia.core.aml import WorkspaceUtils

logging.basicConfig(
    format="[%(levelname)s][%(module)s] %(message)s", level=logging.ERROR
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def run_local_pipeline():
    """
    Called when you pass in the "--local" flag.
    """
    logger.info("Running your pipeline locally.")

    from steps.components import preprocess, train

    preprocess_output = preprocess.preprocess(use_test_dataset="True")
    train.train(input=preprocess_output, outputs_folder="./", train_test_ratio=0.75)


def run_aml_pipeline(args, extra_args):
    """
    Called when you DON'T pass in the "--local" flag.
    Uses AzureML to execute what you pass into "--action".
    """
    logger.info("Using AzureML to execute your provided action.")

    workspace_name: str = args.workspace_name
    env: str = args.env
    action: str = args.action
    publish_datastore_name: str = args.publish_datastore_name
    publish_datastore_path: str = args.publish_datastore_path
    use_workspace_name_for_rg: bool = args.use_workspace_name_for_rg

    pipeline_name: str = f"{workspace_name}-{env}"
    compute_name: str = "DS3-v2-cluster"

    current_dir: str = os.getcwd()
    ischia_config_path: str = os.path.join(current_dir, "default_ischia_config.json")
    pipeline_steps_path: str = os.path.join(current_dir, "steps")

    override_keys: list = list(map(lambda s: s.strip("--"), extra_args[::2]))
    ischia_config_overrides: dict = dict(zip(override_keys, extra_args[1::2]))

    run_aml_job(
        workspace_name=workspace_name,
        env=env,
        action=action,
        publish_datastore_name=publish_datastore_name,
        publish_datastore_path=publish_datastore_path,
        pipeline_name=pipeline_name,
        compute_name=compute_name,
        ischia_config_path=ischia_config_path,
        pipeline_steps_path=pipeline_steps_path,
        ischia_config_overrides=ischia_config_overrides,
        use_workspace_name_for_rg=use_workspace_name_for_rg,
    )


def run_aml_job(**kwargs):
    """
    Called by run_aml_pipeline().
    Figures out whether to publish your AML pipeline or submit it as an AML experiment.
    """
    logger.info(f"Azure Machine Learning SDK Version: {VERSION}")

    ischia_config_overrides: dict = kwargs["ischia_config_overrides"]
    if (
        kwargs["use_workspace_name_for_rg"] is True
        and "resource_group" not in ischia_config_overrides
    ):
        ischia_config_overrides["resource_group"] = kwargs["workspace_name"]
    logger.info(f"Ischia config overrides: {ischia_config_overrides}")

    ischia_config: dict = Config.from_file_path(kwargs["ischia_config_path"])
    workspace_utils: WorkspaceUtils = WorkspaceUtils(
        workspace_name=kwargs["workspace_name"],
        config=ischia_config,
        skip_ds_registration=False,
        **ischia_config_overrides,
    )
    workspace: Workspace = workspace_utils.get_workspace()

    aml_pipeline: Pipeline = create_pipeline(
        workspace=workspace,
        compute_name=kwargs["compute_name"],
        pipeline_steps_path=kwargs["pipeline_steps_path"],
    )
    validate_pipeline(aml_pipeline)

    if args.action == "submit-experiment":
        submit_experiment(
            workspace=workspace,
            aml_pipeline=aml_pipeline,
            experiment_name=kwargs["pipeline_name"],
        )
    elif args.action == "publish-pipeline":
        published_pipeline: PublishedPipeline = publish_pipeline(
            aml_pipeline=aml_pipeline, pipeline_name=kwargs["pipeline_name"]
        )
        if kwargs["publish_datastore_path"] != "":
            upload_published_pipeline_id(
                workspace=workspace,
                datastore_name=kwargs["publish_datastore_name"],
                datastore_path=kwargs["publish_datastore_path"],
                published_pipeline_id=published_pipeline.id,
                pipeline_name=kwargs["pipeline_name"],
            )


def create_pipeline(workspace, compute_name, pipeline_steps_path) -> Pipeline:
    """
    Called by run_aml_job().
    Creates an AML Pipeline object to either submit as an experiment or publish.
    """
    logger.info("Creating your pipeline.")
    compute: RunConfiguration = get_or_create_compute(
        workspace=workspace, compute_name=compute_name
    )
    pipeline_steps: list = create_pipeline_steps(
        workspace=workspace, compute=compute, pipeline_steps_path=pipeline_steps_path
    )
    aml_pipeline: Pipeline = Pipeline(workspace=workspace, steps=pipeline_steps)
    logger.info("Your pipeline was created.")
    return aml_pipeline


def get_or_create_compute(workspace, compute_name) -> RunConfiguration:
    """
    Called by run_aml_job().
    Defines the compute of your AML Pipeline.
    """
    try:
        cpu_cluster = ComputeTarget(workspace=workspace, name=compute_name)
        logger.info("Found existing compute, using it.")
    except ComputeTargetException:
        compute_config = AmlCompute.provisioning_configuration(
            vm_size="Standard_DS3_v2", max_nodes=4, idle_seconds_before_scaledown=300
        )
        cpu_cluster = ComputeTarget.create(
            workspace=workspace,
            name=compute_name,
            provisioning_configuration=compute_config,
        )

    cpu_cluster.wait_for_completion(show_output=True)

    run_amlcompute: RunConfiguration = RunConfiguration()
    run_amlcompute.target = cpu_cluster
    run_amlcompute.environment.docker.enabled = True
    run_amlcompute.environment.docker.base_image = DEFAULT_CPU_IMAGE
    run_amlcompute.environment.python.user_managed_dependencies = False

    conda_deps: CondaDependencies = CondaDependencies()
    conda_deps.add_pip_package("scikit-learn")
    run_amlcompute.environment.python.conda_dependencies = conda_deps

    return run_amlcompute


def create_pipeline_steps(workspace, compute, pipeline_steps_path) -> list:
    """
    Called by run_aml_job().
    Defines steps and data dependencies within your pipeline.
    """
    use_test_dataset = PipelineParameter(name="use_test_dataset", default_value="False")
    train_test_ratio = PipelineParameter(name="train_test_ratio", default_value=0.80)

    default_datastore = workspace.get_default_datastore()
    data_path = DataReference(
        datastore=default_datastore,
        data_reference_name="data_path",
        path_on_datastore="folder/on/default_datastore/my_data.csv",
    )
    data_for_train = PipelineData("data_for_train", datastore=default_datastore)
    outputs_folder = PipelineData("outputs_folder", datastore=default_datastore)

    preprocess_step = PythonScriptStep(
        name="01_preprocess_step",
        inputs=[data_path],
        outputs=[data_for_train],
        source_directory=pipeline_steps_path,
        runconfig=compute,
        script_name="01_preprocess_step.py",
        arguments=[
            "--data_path",
            data_path,
            "--preprocess_output",
            data_for_train,
            "--use_test_dataset",
            use_test_dataset,
        ],
        allow_reuse=False,
    )

    train_step = PythonScriptStep(
        name="02_train_step",
        inputs=[data_for_train],
        outputs=[outputs_folder],
        source_directory=pipeline_steps_path,
        runconfig=compute,
        script_name="02_train_step.py",
        arguments=[
            "--train_input",
            data_for_train,
            "--outputs_folder",
            outputs_folder,
            "--train_test_ratio",
            train_test_ratio,
        ],
        allow_reuse=False,
    )

    pipeline_steps = [preprocess_step, train_step]
    return pipeline_steps


def validate_pipeline(aml_pipeline) -> None:
    """
    Called by run_aml_job() and always runs no matter what you pass in for "--action".
    Validates your AML pipeline.
    """
    logger.info("Validating pipeline.")
    error_list = aml_pipeline.validate()
    if error_list:
        logger.error("Errors found in pipeline:")
        logger.error(error_list)
        raise

    logger.info("Your pipeline was successfully validated.")


def submit_experiment(workspace, aml_pipeline, experiment_name) -> None:
    """
    Called by run_aml_job() and runs when you pass in "--action submit-experiment".
    Submits your pipeline as an AML experiment.
    """
    logger.info("Submitting your pipeline as an experiment.")
    experiment: Experiment = Experiment(workspace=workspace, name=experiment_name)
    pipeline_run: Run = experiment.submit(
        aml_pipeline,
        regenerate_outputs=False,
        pipeline_parameters=define_pipeline_parameters(),
    )
    logger.info("Your pipeline was submitted as an experiment.")
    pipeline_run.wait_for_completion(show_output=True, raise_on_error=True)
    logger.info("Your experiment completed successfully.")


def define_pipeline_parameters() -> dict:
    """
    Called by submit_experiment().
    Defines pipeline parameters to use when submitting the pipeline as an AML experiment.
    Note: AzureML converts booleans to strings so it's recommended to use only strings and numbers for PipelineParameters.
    """
    return {"use_test_dataset": "True", "train_test_ratio": 0.75}


def publish_pipeline(aml_pipeline, pipeline_name) -> str:
    """
    Called by run_aml_job() and runs when you pass in "--action publish-pipeline".
    Publishes your AML pipeline as an endpoint.
    """
    logger.info("Publishing your pipeline.")
    published_amlpipeline = aml_pipeline.publish(
        name=pipeline_name,
        description="Published pipeline",
        version=0.1,
        continue_on_step_failure=False,
    )
    logger.info("Your pipeline was published successfully.")
    logger.info(f"*** Published Pipeline ID: {published_amlpipeline.id} ***")
    return published_amlpipeline


def upload_published_pipeline_id(
    workspace, datastore_name, datastore_path, published_pipeline_id, pipeline_name
) -> None:
    """
    Called by run_aml_job() and runs when you pass in the option parameters "--publish_datastore_name" and "--publish_datastore_path".
    Uploads a CSV containing your Published Pipeline ID to your chosen datastore and path.
    """
    logger.info("Uploading your Published Pipeline ID")

    if datastore_name == "":
        logger.info("No datastore given, using workspace default.")
        ds = workspace.get_default_datastore()
    else:
        logger.info(f"Using datastore {datastore_name}")
        ds = workspace.datastores[datastore_name]

    local_file_name = pipeline_name + ".csv"
    file = open(local_file_name, "w")
    file.write(f"id\n{published_pipeline_id}")
    file.close()

    logger.info(f"Uploading to Azure Storage as blob: {local_file_name}")
    ds.upload_files([local_file_name], target_path=datastore_path, overwrite=True)
    os.remove(local_file_name)

    logger.info("Your Published Pipeline ID was successfully uploaded.")


if __name__ == "__main__":
    local_help = "Specify this flag to run your pipeline logic on your local devbox. You don't need to specify other params."
    workspace_name_help = "Name of workspace to get/create."
    env_help = "Name of environment. This can be your devbox (ex: <alias>-devbox) or a repo branch (ex: develop)."
    action_help = "Action to take using AzureML. Valid options are: submit-experiment, publish-pipeline."
    publish_datastore_name_help = (
        "(Optional) Datastore name to upload your Published Pipeline ID to."
    )
    publish_datastore_path_help = (
        "(Optional) Folder path on datastore to upload your Published Pipeline ID to."
    )
    use_workspace_name_for_rg_help = "(Optional) By default, your workspace_name parameter is used for the resource group name. Specify this flag if you DON'T want this."

    parser = argparse.ArgumentParser("Process arguments to execute the driver file.")
    parser.add_argument("--local", action="store_true", help=local_help)
    parser.add_argument("--workspace_name", type=str, help=workspace_name_help)
    parser.add_argument("--env", type=str, help=env_help)
    parser.add_argument("--action", type=str, default="validate", help=action_help)
    parser.add_argument(
        "--publish_datastore_name",
        type=str,
        default="",
        help=publish_datastore_name_help,
    )
    parser.add_argument(
        "--publish_datastore_path",
        type=str,
        default="",
        help=publish_datastore_path_help,
    )
    parser.add_argument(
        "--use_workspace_name_for_rg",
        action="store_false",
        help=use_workspace_name_for_rg_help,
    )
    args, extra_args = parser.parse_known_args()

    if args.local is True:
        run_local_pipeline()
    else:
        run_aml_pipeline(args, extra_args)
