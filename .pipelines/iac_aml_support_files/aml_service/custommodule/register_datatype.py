import sys
import argparse
from azureml.core import Workspace
from azureml.pipeline.core.graph import DataType
from azureml.core.authentication import ServicePrincipalAuthentication

if __name__ == '__main__':
    parse = argparse.ArgumentParser()
    
    parse.add_argument('--AZUREML_RESOURCEGROUP')
    parse.add_argument('--AZUREML_WORKSPACE_NAME')
    parse.add_argument('--AZUREML_SUBSCRIPTION_ID')
    parse.add_argument('--TENANT_ID')
    parse.add_argument('--APP_ID')
    parse.add_argument('--APP_SECRET')

    args = parse.parse_args()

    TENANT_ID = args.TENANT_ID
    APP_ID = args.APP_ID
    APP_SECRET = args.APP_SECRET
    WORKSPACE_NAME = args.AZUREML_WORKSPACE_NAME
    SUBSCRIPTION_ID = args.AZUREML_SUBSCRIPTION_ID
    RESOURCE_GROUP = args.AZUREML_RESOURCEGROUP

    SP_AUTH = ServicePrincipalAuthentication(
        tenant_id=TENANT_ID,
        service_principal_id=APP_ID,
        service_principal_password=APP_SECRET)

    ws = Workspace.get(
        WORKSPACE_NAME,
        SP_AUTH,
        SUBSCRIPTION_ID,
        RESOURCE_GROUP
    )    

    try:
        # make sure built-in datetype get refresh and become available    
        data_types = DataType.list_data_types(ws)
        for d in data_types:
            print(d.name)
        
        # register DateType ModelDirectory and DateFrameDirectory
        DataType.create_data_type(ws, "ModelDirectory", "ModelDirectory datatype", True, parent_datatypes=None)
        DataType.create_data_type(ws, "DataFrameDirectory", "DataFrameDirectory datatype", True, parent_datatypes=None)

        print("DateType ModelDirectory and DataFrameDirectory registered successfully")
    except Exception as caught_error:
        print("Error while registering DataType: " + str(caught_error))
        sys.exit(1)