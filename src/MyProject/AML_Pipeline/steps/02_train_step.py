import argparse
import logging

from components import train

from azureml.core import VERSION
from azureml.core.model import Model
from azureml.core.run import Run
import pandas as pd

run = Run.get_context()

logging.basicConfig(format="[%(levelname)s][%(module)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.info(f"Azure Machine Learning SDK Version: {VERSION}")

parser = argparse.ArgumentParser()
parser.add_argument("--train_input", type=str)
parser.add_argument("--outputs_folder", type=str)
parser.add_argument("--train_test_ratio", type=float)
args = parser.parse_args()

train_input: pd.DataFrame = pd.read_parquet(args.train_input)

model_file_path: str = train.train(
    input=train_input,
    outputs_folder=args.outputs_folder,
    train_test_ratio=args.train_test_ratio,
)

registered_model: Model = Model.register(
    model_path=model_file_path,
    model_name="My_Model",
    description="My Model Description",
    workspace=run.experiment.workspace,
)
