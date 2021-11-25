import argparse
import logging

from components import preprocess

from azureml.core import VERSION
from azureml.core.run import Run
import pandas as pd

run = Run.get_context()

logging.basicConfig(format="[%(levelname)s][%(module)s] %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.info(f"Azure Machine Learning SDK Version: {VERSION}")

parser = argparse.ArgumentParser()
parser.add_argument("--use_test_dataset", type=str)
parser.add_argument("--data_path", type=str)
parser.add_argument("--preprocess_output", type=str)
args = parser.parse_args()

preprocess_output: pd.DataFrame = preprocess.preprocess(
    use_test_dataset=args.use_test_dataset, data_path=args.data_path
)

preprocess_output.to_parquet(args.preprocess_output)
