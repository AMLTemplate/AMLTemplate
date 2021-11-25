import logging

import pandas as pd
from sklearn import datasets
from sklearn.utils import Bunch

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def preprocess(use_test_dataset: str, data_path: str = "") -> pd.DataFrame:
    logger.info("Starting preprocessing")

    my_df: pd.DataFrame = None

    if use_test_dataset == "True":
        logger.info(f"use_test_dataset: {use_test_dataset} -> Using test dataset")
        boston: Bunch = datasets.load_boston()
        my_df: pd.DataFrame = pd.DataFrame(boston.data, columns=boston.feature_names)
        my_df["target"] = boston.target
    else:
        logger.info(f"use_test_dataset: {use_test_dataset} -> Using {data_path}")
        my_df = pd.read_csv(data_path)

    logger.info("Completed preprocessing")

    return my_df
