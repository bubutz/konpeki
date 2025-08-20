#!/usr/bin/env python3

import requests
import json
import os
import sys
import shutil
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential, ClientSecretCredential, InteractiveBrowserCredential

# List of subscriptions to gather details
# Sub name : Sub ID
all_subs = {
    "A01": "abcdefgh-ijkl-mnop-qrst-000000000001",
    "B01": "abcdefgh-ijkl-mnop-qrst-000000000002",
    "C01": "abcdefgh-ijkl-mnop-qrst-000000000003",
    "D01": "abcdefgh-ijkl-mnop-qrst-000000000004",
    "E01": "abcdefgh-ijkl-mnop-qrst-000000000005",
    "F01": "abcdefgh-ijkl-mnop-qrst-000000000006",
    "G01": "abcdefgh-ijkl-mnop-qrst-000000000007",
    "H01": "abcdefgh-ijkl-mnop-qrst-000000000008",
    "I01": "abcdefgh-ijkl-mnop-qrst-000000000009",
    "J01": "abcdefgh-ijkl-mnop-qrst-000000000010",
    "K01": "abcdefgh-ijkl-mnop-qrst-000000000011",
    "L01": "abcdefgh-ijkl-mnop-qrst-000000000012",
    "M01": "abcdefgh-ijkl-mnop-qrst-000000000013"
}

# As of 2023 March, below 3 are the only for hosting AI related services
# TODO: Solve how to generate list below instead of hardcoded list
resource_types = [
    "Microsoft.CognitiveServices/accounts",
    "Microsoft.Search/searchServices",
    "Microsoft.BotService/botServices"
]

# Required variables
# TODO: Change from try except to use getopts
#       job_id is Ansible's Job ID, used to create unique tmpfile name.
#         Change to something like linux mktemp
try:
    job_id = int(sys.argv[1])
    scan_type = sys.argv[2]
    result_file = sys.argv[3]
except:
    sys.exit("Error with command line arguments input. Please check")

# Below to set start and end time for resources usage based on the jobtype set above
time_now = datetime.now()
if scan_type == "Monthly":
    if time_now.month =< 1:
        last_month = 12
    else:
        last_month = time_now.month - 1
    time_start = datetime(time_now.year, last_month, 1, 0, 0, 0, 0)
    time_end = time_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
elif scan_type == "Weekly":
    num_of_days = 7
    time_end = time_now.replace(hour=0, minute=0, second=0, microsecond=0)
    time_start = time_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=num_of_days)
else: # This implies daily
    num_of_days = 1
    time_start = time_now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=num_of_days)

timespan = f"{time_start.isoformat()}Z/{time_end.isoformat()}Z"
today = f"{time_now.year}={'{:02d}'.format(time_now.month)}-{'{:02d}'.format(time_now.day)}"

log_dir = f"/tmp/aimetric_{scan_type}_{today}_{job_id}"

# File contains Service Principal credentials
load_dotenv('/root/.sp_cred')
credential = ClientSecretCredential(
    client_id=os.getenv("sp_client_id"),
    client_secret=os.getenv("sp_client_secret"),
    tenand_id=os.getenv("sp_tenant_id")
)
token = credential.get_token("https://management.azure.com/.default").token

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

# Retrieve all resources from the sub in all_sub, and with type in resources_types
# TODO: Move this into function or class
all_resources = {}
for res_type in resource_types:
    filter_param = f"resourceType eq '{res_type}'"
    encoded_filter_param = requests.utils.quote(filter_param)

    for sub in all_subs:
        api_url = f"https://management.azure.com/subscriptions/{all_subs[sub]}/resources?$filter={encoded_filter_param}&api-version=2021-04-01"

        response = requests.get(api_url, headers=headers)
        response.status_code

        # Store details into the dict
        try:
            for item in response.json()['value']:
                all_resources[item['id']] = [item['name'], sub, item['kind'], res_type]
        except:
            try:
                for item in response.json()['value']:
                    all_resources[item['id'].strip()] = [item['name'], sub, res_type.split('/')[1], res_type]
            except:
                print(response.json())

# Create a set to contain unique subscription name that has ai resources
bu_with_resources = set()
for res_id in all_resources:
    bu_with_resources.add(all_resources[res_id][1])


# Generate report 1 csv for each subscription
# TODO: move this to function, or class method
os.makedirs(log_dir)
for bu in bu_with_resources:
    log_file = f"{log_dir}/{bu}-{scan_type}-{today}.csv"
    stdout_fileno = sys.stdout
    sys.stdout = open(log_file, 'w')
    print("Resource Name,Provider,Metric,Datetime,Value")

    for resource_id in all_resources:

        api_url = "https://management.azure.com{resource_id}/providers/microsoft.insights/metrics?api-version=2023-10-01"
        api_definition_url = "https://management.azure.com{resource_id}/providers/Microsoft.Insights/metricDefinitions?api-version=2023-10-01"

        if all_resources[resource_id][1] == bu:

            if all_resources[resource_id][3] == "Microsoft.Search/searchServices":
                
                params = {
                    "metricnames": "SkillExecutionCount,DocumentProcessedCount",
                    "timespan": timespan,
                    "interval": "PT1H",
                    # "aggregation": "Count"
                    "aggregation": "Total"
                }
                response = requests.get(api_url.format(resource_id=resource_id), headers=headers, params=params)
                response.status_code

                metrics_data = response.json()
                for metric in metrics_data['value']:
                    for timeseries in metric['timeseries']:
                        for data in timeseries['data']:
                            time = data['timeStamp']
                            total = data.get('average', 0)
                            print(f"{all_resources[resource_id][0]},{all_resources[resource_id][2]},{metric['name']['value']},{time},{total}")

            elif all_resources[resource_id][3] == "Microsoft.BotService/botServices":

                params = {
                    "metricnames": "RequestsTraffic",
                    "timespan": timespan,
                    "interval": "PT1H",
                    # "aggregation": "Count"
                    "aggregation": "Total"
                }
                response = requests.get(api_url.format(resource_id=resource_id), headers=headers, params=params)
                response.status_code

                metrics_data = response.json()
                for metric in metrics_data['value']:
                    for timeseries in metric['timeseries']:
                        for data in timeseries['data']:
                            time = data['timeStamp']
                            total = data.get('average', 0)
                            print(f"{all_resources[resource_id][0]},{all_resources[resource_id][2]},{metric['name']['value']},{time},{total}")

            else:

                params = {
                    "metricnames": "TotalCalls",
                    "timespan": timespan,
                    "interval": "PT1H",
                    # "aggregation": "Count"
                    "aggregation": "Total"
                }
                response = requests.get(api_url.format(resource_id=resource_id), headers=headers, params=params)
                response.status_code

                metrics_data = response.json()
                for metric in metrics_data['value']:
                    for timeseries in metric['timeseries']:
                        for data in timeseries['data']:
                            time = data['timeStamp']
                            total = data.get('average', 0)
                            print(f"{all_resources[resource_id][0]},{all_resources[resource_id][2]},{metric['name']['value']},{time},{total}")

    # Close file handler once completed one subscription
    sys.stdout.close()
sys.stdout = stdout_fileno

# Consolidate all csv into 1 excel
shutil.make_archive(result_file, 'zip', log_dir)
csv_dir = log_dir
csv_files = os.listdir(csv_dir)
excel_output = f"{result_file}.xlsx"

with pd.ExcelWriter(excel_output) as writer:
    for csv_file in csv_files:
        p = Path(f"{log_dir}/{csv_file}")
        sheet_name = p.stem[:31]
        # print(sheet_name)
        df = pd.read_csv(p)
        df.to_excel(writer, sheet_name=sheet_name, index=None, header=True)

shutil.rmtree(log_dir)
