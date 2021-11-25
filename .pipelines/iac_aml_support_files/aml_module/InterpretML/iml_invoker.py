import os
import sys
import argparse
import joblib
import uuid
import pandas as pd
from pathlib import Path
from enum import Enum
from azureml.studio.core.data_frame_schema import DataFrameSchema
from azureml.studio.core.logger import module_logger as logger
from azureml.studio.core.io.data_frame_directory import load_data_frame_from_directory, save_data_frame_to_directory
from azureml.studio.core.io.model_directory import load_model_from_directory
from azureml.core.run import Run
from interpret.ext.blackbox import TabularExplainer
from azureml.contrib.interpret.explanation.explanation_client import ExplanationClient


class ModelSourceType(Enum):
    ModelDirectory = 'From ModelDirectory'
    Workspace = 'Registered in Workspace'


class IMLExplainer:
    def __init__(self, exp_client, model, registeredModelId, input_train_data, input_test_data, feature_names=None):
        self._exp_lient = exp_client
        self._model = model
        self._modelId = registeredModelId
        self._input_train_data = input_train_data
        self._input_test_data = input_test_data
        self._feature_names = feature_names

    @property
    def model(self):
        return self._model

    @property
    def input_train_data(self):
        return self._input_train_data

    @property
    def input_test_data(self):
        return self._input_test_data

    def get_global_explanation(self):
        # Explain predictions

        logger.debug(f'model type {type(self.model)}.')

        logger.debug(f'input_train_data shape: {self.input_train_data.shape}')
        logger.debug(f'input_train_data: \n: {self.input_train_data}')
        logger.debug(f'input_test_data shape: {self.input_test_data.shape}')
        logger.debug(f'input_test_data: \n: {self.input_test_data}')

        if self._feature_names:
            tabular_explainer = TabularExplainer(
                self.model, self.input_train_data, features=self._feature_names)
        else:
            tabular_explainer = TabularExplainer(
                self.model, self.input_train_data)

        # Explain overall model predictions (global explanation)
        return tabular_explainer.explain_global(self.input_test_data)

    def get_and_upload_global_explanation(self):
        comment = f'Global explanation on trained model {self.model}'
        explanation = self.get_global_explanation()
        self._exp_lient.upload_model_explanation(
            explanation, comment=comment, model_id=self._modelId)

        names = explanation.get_ranked_global_names()
        values = explanation.get_ranked_global_values()
        ranks = explanation.global_importance_rank

        lst = list(zip(names, values, ranks))
        result_df = pd.DataFrame(
            lst, columns=['FeatureName', 'ImportanceValue', 'ImportanceRank'], dtype=float)
        logger.info(f"explanation results: \n {result_df}")
        return result_df


def joblib_loader(load_from_dir, model_spec):
    file_name = model_spec['file_name']
    file_path = Path(load_from_dir) / file_name
    with open(file_path, 'rb') as fin:
        return joblib.load(fin)


def load_binary(filepath):
    try:
        return joblib.load(filepath)
    except:
        import pickle
        with open(filepath, 'rb') as f:
            return pickle.load(f)


if __name__ == '__main__':

    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--trained-model', help='The directory contains trained model.')
    parser.add_argument(
        '--trained-model-name', help='The directory contains data frame which have the trained model name .')
    parser.add_argument(
        '--dataset-to-train', help='Dataset used in train')
    parser.add_argument(
        '--dataset-to-test', help='Dataset to test')
    parser.add_argument(
        '--feature-names', help='The names of the features (comma separated)')
    parser.add_argument(
        '--model-source-type', help='Modele source type, can be \'From ModelDirectory\' or \'Registered in Workspace\'')
    parser.add_argument(
        '--explanation-result', help='Output of explanation')

    args, _ = parser.parse_known_args()

    logger.info(f"Arguments: {args}")

    dataset_to_train = load_data_frame_from_directory(
        args.dataset_to_train).data
    logger.debug(f"Shape of loaded DataFrame dataset_to_train: {dataset_to_train.shape}")

    dataset_to_test = load_data_frame_from_directory(args.dataset_to_test).data
    logger.debug(f"Shape of loaded DataFrame dataset_to_test: {dataset_to_test.shape}")

    input_features = None
    if args.feature_names:
        input_features = args.feature_names.split(",")
        logger.debug(f"input_features: {input_features}")

    run = Run.get_context()

    modelSource = ModelSourceType(args.model_source_type)

    if modelSource == ModelSourceType.ModelDirectory:
        modelObj = load_model_from_directory(
            args.trained_model, model_loader=joblib_loader).data
        trained_model = modelObj.model
        logger.info(f"Load trained model {trained_model} successfully from {args.trained_model}")
    elif modelSource == ModelSourceType.Workspace:
        from azureml.core.model import Model
        modelName_df = load_data_frame_from_directory(
            args.trained_model_name).data
        modelName = modelName_df['ModelName'][0]
        logger.debug(f"model to load: {modelName}")
        if modelName is None:
            raise Exception(
                'The up dependency should output ModelName in dataframe. pd.DataFrame({\'ModelName\':[model_name]})')
        ws = run.experiment.workspace
        model_path = Model.get_model_path(model_name=modelName)
        trained_model = load_binary(model_path)
        logger.info(f"Load trained model {trained_model} successfully from {model_path}")

    # dump model to local folder, upload and register model with current experiment run
    # this is to get model.id for IML Api
    model_file_name = 'model.pkl'
    with open(model_file_name, 'wb') as file:
        joblib.dump(value=trained_model, filename=model_file_name)

    run.upload_file(name=model_file_name, path_or_stream=model_file_name)
    registered_model = run.register_model(
        model_name="model_" + str(uuid.uuid4().node), model_path=model_file_name)

    # use IML to get and upload model explanation
    iml_exp = IMLExplainer(ExplanationClient.from_run(run),
                           trained_model,
                           registered_model.id,
                           dataset_to_train,
                           dataset_to_test,
                           input_features)

    explanation_df = iml_exp.get_and_upload_global_explanation()

    save_data_frame_to_directory(
        args.explanation_result,
        explanation_df,
        schema=DataFrameSchema.data_frame_to_dict(explanation_df),
    )
