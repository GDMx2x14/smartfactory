from kpi_dataframe_filter import kpi_dataframe_filter
from kpi_data_extraction import kpi_dataframe_data_extraction
import pandas as pd
import requests, os
from sympy import symbols, parse_expr, SympifyError

class kpi_engine:
    
    def dynamic_kpi(df, machine_id, machine_type, start_period, end_period, kpi_id):
        fd = df
        # kpi_formula = extract formula through API and kpi_id
        headers = {
            "x-api-key": "b3ebe1bb-a4e7-41a3-bbcc-6c281136e234",
            "Content-Type": "application/json"
        }
        response = requests.get(f"http://kb:8000/kb/{kpi_id}/get_kpi", headers=headers)
        response = response.json()
        if response.get("atomic") == True:
            formula = response.get("id")
            aggregator = formula[-3:]
        else:
            formula = response.get("atomic_formula")
            aggregator = "-"
        unit_of_measure = response.get("unit_measure")

        try:
            print(f"({kpi_id}) FORMULA = {formula}\n")
            expr = parse_expr(formula)
        except Exception as e:
            return "Error: the specified KPI was not found in the Knowledge Base", "-", "-"

        # data extraction and symbol substitution
        substitutions = {}
        for symbol in expr.free_symbols:
            data_extraction_method = getattr(kpi_dataframe_data_extraction, str(symbol)[-3:]+"_kpi")
            try:
                substitutions[symbol] = data_extraction_method(df=df, kpi=str(symbol)[:-4], machine_id=machine_id, machine_type=machine_type, start_period=start_period, end_period=end_period)
            except ValueError as e:
                return str(e), "-"

            result = expr.subs(substitutions)
        print(f"EXPR = {expr}\n")
        print(f"SUBST = {substitutions} \n")
        print(f"RESULT = {result}\n\n")


        # formula evaluation
        eval_result = result.evalf()
        return float(eval_result), unit_of_measure, aggregator