from kpi_calculation import kpi_engine
from fastapi import FastAPI, HTTPException
import pandas as pd
from typing import List
import uvicorn
import requests
from pydantic import BaseModel
import os, time
from pathlib import Path
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from api_auth.api_auth import get_verify_api_key
from fastapi import Depends

from kpi_dataframe_update import kpi_dataframe_update

env_path = Path(__file__).resolve().parent.parent / ".env"
print(env_path)
load_dotenv(dotenv_path=env_path)

'''
# Only for testing purposes
with open("../smart_app_data.pkl", "rb") as file:
    df = pd.read_pickle(file)
'''

headers = {
    "Content-Type": "application/json",
    "x-api-key": "06e9b31c-e8d4-4a6a-afe5-fc7b0cc045a7"
}
druid_url = "http://router:8888/druid/v2/sql"
query_body = {
        "query": "SELECT * FROM \"timeseries\""
    }

success = False
while not success:
    try:
        response = requests.post(druid_url, headers=headers, json=query_body)
        response.raise_for_status()  # Raise an error for bad status codes
        df = response.json()  # Return the JSON response
        success = True
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        time.sleep(5)

df = pd.DataFrame.from_dict(df, orient='columns')

df.rename(columns={"__time": "time"}, inplace=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class KPIRequest(BaseModel):
    What_If_KPI: Optional[List[str]] = ["NULL"]
    What_If_Change: Optional[List[str]] = ["0"]
    KPI_Name: Optional[str] = "no_kpi"
    Machine_Name: Optional[str] = "all_machines"
    Machine_Type: Optional[str] = "any"
    Date_Start: Optional[str] = df['time'].min()[:10]
    Date_Finish: Optional[str] = df['time'].max()[:10]
    Aggregator: Optional[str] = 'sum'
    startPreviousPeriod: Optional[str] = df['time'].min()[:10]
    endPreviousPeriod: Optional[str] = df['time'].max()[:10]

@app.post("/kpi")
async def read_root():
    return {"message": "Welcome to the KPI Calculation Engine!"}

@app.post("/kpi/calculate")
async def calculate(request: List[KPIRequest], api_key: str = Depends(get_verify_api_key(["ai-agent", "api-layer"]))): # to add or modify the services allowed to access the API, add or remove them from the list in the get_verify_api_key function e.g. get_verify_api_key(["gui", "service1", "service2"])
    # print(f"Received request: {request}")

    def process_single_request(req: KPIRequest):
        try:
            kpiID = req.KPI_Name
            machineId = req.Machine_Name
            machineType = req.Machine_Type
            startPeriod = req.Date_Start
            endPeriod = req.Date_Finish
            aggregator = req.Aggregator
            unitOfMeasure = 'UoM'
            startPreviousPeriod = req.startPreviousPeriod
            endPreviousPeriod = req.endPreviousPeriod
            what_if_changes= req.What_If_Change
            what_if_kpis = req.What_If_KPI
            percentage_difference = "-"
        
            if(kpiID == "dynamic_kpi"):
                raise HTTPException(status_code=404, detail=f"'dynamic_kpi' method not directly callable.")

            # If the requested KPI is not in the static methods, call the dynamic KPI method. Otherwise, just call the good old static one
            if kpiID == "no_kpi":
                value = "Error: KPI name is required"
                unitOfMeasure = "-"
                aggregator = "-"
            elif what_if_changes == ["0"]:
                value, unitOfMeasure, aggregator = kpi_engine.dynamic_kpi(df = df, machine_id = machineId, start_period = startPeriod, end_period = endPeriod, machine_type = machineType, kpi_id=kpiID)         
            else:
                # what-if use case
                # the dataframe have to change according to what-if
                fd = kpi_dataframe_update.update_df(df.copy(),what_if_kpis,what_if_changes,machineId)
                result, unitOfMeasure, aggregator = kpi_engine.dynamic_kpi(df = df, machine_id = machineId, start_period = startPeriod, end_period = endPeriod, machine_type = machineType, kpi_id=kpiID)
                result_, unitOfMeasure, aggregator = kpi_engine.dynamic_kpi(df = fd, machine_id = machineId, start_period = startPeriod, end_period = endPeriod, machine_type = machineType, kpi_id=kpiID)                 
                value=[result,result_]
                percentage_difference = result_/result
                if percentage_difference >=1:
                    percentage_difference=f"+{(percentage_difference-1)*100} %"
                else:
                    percentage_difference = f"-{(1-percentage_difference)*100} %"
            return {
                "Machine_Name": machineId,
                "Machine_Type": machineType,
                "KPI_Name": kpiID,
                "Value": value,
                "Measure_Unit": unitOfMeasure,
                "Date_Start": startPeriod,
                "Date_Finish": endPeriod,
                "Aggregator": aggregator,
                "Forecast": False,
                "Percentage_Difference": percentage_difference
            }
        except Exception as e:
            print("LOG EXC")
            return {
                "Machine_Name": machineId,
                "Machine_Type": machineType,
                "KPI_Name": kpiID,
                "Value": "Error: " + str(e),
                "Measure_Unit": "-",
                "Date_Start": startPeriod,
                "Date_Finish": endPeriod,
                "Aggregator": "-",
                "Forecast": False,
                "Percentage_Difference": percentage_difference
            }
    
    response = [process_single_request(req) for req in request]
    if len(response) == 0:
        return [{"Value": "Error: Request input not valid"}]
    print(f"RESPONSE ========>>>>>>>>>>>>>>> \n{response}")
    return response

if __name__ == "__main__":
    uvicorn.run(app, host=os.getenv("KB_HOST"), port=int(os.getenv("KB_PORT")))