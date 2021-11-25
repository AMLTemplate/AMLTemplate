import joblib
import logging
import os

import pandas as pd
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def train(input: pd.DataFrame, outputs_folder: str, train_test_ratio: float) -> str:
    logger.info("Starting training")

    logger.info(f"Using train/test ratio of {train_test_ratio}")
    (features_train, features_test, label_train, label_test,) = train_test_split(
        input.drop(["target"], axis=1), input[["target"]], train_size=train_test_ratio
    )

    model = LinearRegression()
    model.fit(features_train, label_train)
    label_pred = model.predict(features_test)

    mse = mean_squared_error(label_test, label_pred)
    r2 = r2_score(label_test, label_pred)

    logger.info(f"Model Coefficients: {model.coef_}")
    logger.info(f"Model Intercept: {model.intercept_}")
    logger.info("Mean squared error: %.2f" % mse)
    logger.info("Coefficient of determination: %.2f" % r2)

    logger.info("Completed training")
    logger.info(f"Saving model to {outputs_folder}")

    os.makedirs(outputs_folder, exist_ok=True)
    model_file_path = os.path.join(outputs_folder, "model.pkl")
    _ = joblib.dump(model, model_file_path)

    logger.info("Saved model")

    return model_file_path
