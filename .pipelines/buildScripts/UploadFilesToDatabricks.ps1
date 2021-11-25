Param(
    [String]$ClientId,
    [String]$ClientSecret,
    [String]$Tenant,
    [String]$SubscriptionId,
    [String]$ResourceGroupName,
    [String]$WorkspaceName,
    [String]$IncludeFileTypesCsv = "*.py,*.scala,*.ipynb,*.html,*.r",
    [String]$PathOnBuildingAgent, # Path on building agent containing all files that need to be imported into Databricks
    [String]$DatabricksWorkspacePath, # Notebook root path
    [String]$Environment,
    [String]$Language = "PYTHON",
    [bool] $DetectLanguageByExtension = $True,    
    [bool]$IsDBFS = $False
)

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Web
$ServiceUrl = "https://$Environment.azuredatabricks.net/api"

    function UploadAllFiles {
        Param($PathOnBuildingAgent, $IncludeFilesCSV, $DatabricksWorkspacePath, $IsDBFS, $DetectLanguageByExtension, $databricksInformation)
        $PathOnBuildingAgent = (Get-Item -Path $PathOnBuildingAgent).FullName
        $Files = Get-ChildItem -Path $PathOnBuildingAgent -Recurse -Force -Include $IncludeFilesCSV.Split(',') -Name

        if ($Files.count -eq 0)
        {
            Write-Host "It is empty under the script folder $PathOnBuildingAgent, nothing to copy."
		}
        else
        {
            ForEach ($File In $Files) {
                FormatThenMakeDirectory -File $File -IsDBFS $IsDBFS -databricksInformation $databricksInformation
                FormatThenUploadFile -File $File -IsDBFS $IsDBFS -DetectLanguageByExtension $DetectLanguageByExtension -databricksInformation $databricksInformation
            }
        }
    }

    function FormatThenMakeDirectory {
        Param($File, $IsDBFS, $databricksInformation)
        $FileDir = Split-Path -Path $File
        $FileDir = ReplaceBackslashWithForwardSlash -Path $FileDir
        MakeDirectory -DatabricksWorkspacePath "$DatabricksWorkspacePath/$FileDir" -IsDBFS $IsDBFS -databricksInformation $databricksInformation
    }

    function MakeDirectory {
        Param($DatabricksWorkspacePath, $IsDBFS, $databricksInformation)

        $Body = @{
            path = $DatabricksWorkspacePath
        } | ConvertTo-Json

        Write-Host "Making directory $DatabricksWorkspacePath on Databricks"
        CallDatabricksCommand -command "mkdirs" -isDbfs $IsDBFS -body $Body -databricksInformation $databricksInformation
        Write-Host "Made directory $DatabricksWorkspacePath on Databricks"
    }
    
    function GetLanguageByFileExtension {
        Param($File)
        
        $FileExtension = [System.IO.Path]::GetExtension($File)
        switch ($FileExtension) {
            '.py' {
                return "PYTHON"
            }
            
            '.ipynb' {
                return "PYTHON"
            }

            '.scala' {
                return "SCALA"
            }

            '.sql' {
                return "SQL"
            }

            '.r' {
                return "R"
            }
            
            Default {
                throw "Unsupported file extension/language: [$FileExtension]."
            }
        }
    }

    function GetFormateByFileExtension {
        Param($File)
        
        $FileExtension = [System.IO.Path]::GetExtension($File)
        switch ($FileExtension) {
            '.html' {
                return "HTML"
            }
            
            '.ipynb' {
                return "JUPYTER"
            }
            
            Default {
                return "SOURCE"
            }
        }
    }

    function FormatThenUploadFile {
        Param($File, $IsDBFS, $DetectLanguageByExtension, $databricksInformation)

        $LocalFilePath = "$PathOnBuildingAgent\$File"
        $FileWithForwardSlash = ReplaceBackslashWithForwardSlash -Path $File

        if($DetectLanguageByExtension) {
            $Language = GetLanguageByFileExtension $File
        }

        $format = GetFormateByFileExtension $File

        UploadFile -FilePath $LocalFilePath -DatabricksWorkspacePath "$DatabricksWorkspacePath/$FileWithForwardSlash" -Language $Language -Format $format -IsDBFS $IsDBFS -databricksInformation $databricksInformation
    }
    
    function UploadFile {
        Param($FilePath, $DatabricksWorkspacePath, $Language, $Format, $IsDBFS, $databricksInformation)

        $Content = [IO.File]::ReadAllText($FilePath)
        $Bytes = [System.Text.Encoding]::UTF8.GetBytes($Content)
        $Content = [Convert]::ToBase64String($Bytes)

        $Body = @{
            overwrite = $true
            language = $Language
            path = $DatabricksWorkspacePath
            format = $Format
            content = $Content
        } | ConvertTo-Json

        Write-Host "Writing file $FilePath to $DatabricksWorkspacePath"
        CallDatabricksCommand -command "import" -isDbfs $IsDBFS -body $Body -databricksInformation $databricksInformation
        Write-Host "Wrote file $FilePath to $DatabricksWorkspacePath"
    }

    function CallDatabricksCommand($command, $isDbfs, $body, $databricksInformation) {
        if ($isDbfs) {
            $url = "$ServiceUrl/2.0/dbfs/"
        } else {
            $url = "$ServiceUrl/2.0/workspace/"
        }
        $url += $command

        $headers = @{
            "Authorization"="Bearer $($databricksInformation.azureAdAccessToken)";
            "X-Databricks-Azure-SP-Management-Token"=$databricksInformation.managementEndpointAccessToken;
            "X-Databricks-Azure-Workspace-Resource-Id"="/subscriptions/$($databricksInformation.subscriptionId)/resourceGroups/$($databricksInformation.resourceGroupName)/providers/Microsoft.Databricks/workspaces/$($databricksInformation.workspaceName)"
            "Content-Type"="application/json"
        }

        Invoke-RestMethod $url -Body $body -Method Post -UseBasicParsing -Headers $headers
    }

    function ReplaceBackslashWithForwardSlash {
        Param($Path)
        return $Path -replace '\\', '/'
    }

    function GetAzureAdAccessToken($clientId, $clientSecret, $tenant) {
        if (($ClientId -eq $null) -or ($ClientSecret -eq $null) -or ($Tenant -eq $null))
        {
            throw "ClientId, ClientSecret, and Tenant must not be null when calling GetAzureAdAccessToken"
        }
        # Following the guide at https://docs.microsoft.com/en-us/azure/databricks/dev-tools/api/latest/aad/service-prin-aad-token#--get-an-azure-active-directory-access-token
        # azureDatabricksResourceId is a hard-coded value
        $azureDatabricksResourceId = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
        
        $token = GetToken -clientId $clientId -clientSecret $clientSecret -tenant $tenant -resource $azureDatabricksResourceId
        return $token
    }

    function GetAzureManagementResourceToken($clientId, $clientSecret, $tenant) {
        if (($ClientId -eq $null) -or ($ClientSecret -eq $null) -or ($Tenant -eq $null))
        {
            throw "ClientId, ClientSecret, and Tenant must not be null when calling GetAzureManagementResourceToken"
        }

        # Following the guide at https://docs.microsoft.com/en-us/azure/databricks/dev-tools/api/latest/aad/service-prin-aad-token#--use-an-azure-ad-access-token-to-access-the-databricks-rest-api
        # managementResourceEndpoint is a hard-coded value
        $managementResourceEndpoint = "https://management.core.windows.net/"
        
        $token = GetToken -clientId $clientId -clientSecret $clientSecret -tenant $tenant -resource $managementResourceEndpoint
        return $token
    }

    function GetToken($clientId, $clientSecret, $tenant, $resource) {
        $clientIdEncoded = [System.Web.HTTPUtility]::UrlEncode($clientId)
        $clientSecretEncoded = [System.Web.HTTPUtility]::UrlEncode($clientSecret)
        $resourceEncoded = [System.Web.HTTPUtility]::UrlEncode($resource)

        $uri = "https://login.microsoftonline.com/$tenant/oauth2/token"
        $body = "grant_type=client_credentials&client_id=$clientIdEncoded&resource=$resourceEncoded&client_secret=$clientSecretEncoded"

        $result = Invoke-RestMethod $uri -ContentType 'application/x-www-form-urlencoded' -Method Post -Body $body
        return $result.access_token
    }

$azureAdAccessToken = GetAzureAdAccessToken -clientId $ClientId -clientSecret $ClientSecret -tenant $Tenant
$managementEndpointAccessToken = GetAzureManagementResourceToken -clientId $ClientId -clientSecret $ClientSecret -tenant $Tenant
$databricksInformation = @{
    "azureAdAccessToken" = $azureAdAccessToken;
    "managementEndpointAccessToken" = $managementEndpointAccessToken;
    "subscriptionId" = $SubscriptionId;
    "resourceGroupName" = $ResourceGroupName;
    "workspaceName" = $WorkspaceName;
}

UploadAllFiles -PathOnBuildingAgent $PathOnBuildingAgent -IncludeFilesCSV $IncludeFileTypesCsv -Token $token -DatabricksWorkspacePath $DatabricksWorkspacePath -IsDBFS $IsDBFS -DetectLanguageByExtension $DetectLanguageByExtension -databricksInformation $databricksInformation
