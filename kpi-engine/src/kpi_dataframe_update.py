import pandas as pd
import regex as re

class kpi_dataframe_update:
    def _parse_change(change: str):
        # This method parses every kind of 'change' data got from the RAG into the pair (change,operation)
        # change: float -> number to be sostituited/multiplicated/added to the previous dataframe value
        # operation : {*} (for now)
        #TODO: per ora si supporta solo *
        regex =r"([+-])([0-9]+)(\.[0-9]+)?%"
        # The regex match with every +/-NUMBER% string
        temp=re.search(regex,change)
        # The 0 index element is the entire string matched, so the other 3 are +,NUMBER,[.NUMBER] if there is no [.NUMBER] since [.NUMBER] is within (), 
        # the search will return None type as the last element of temp
        #+/-
        op = temp[1]
        value = temp[2] if (temp[3] is None) else temp[2]+temp[3]
        # from percentage to actual number
        value =float(value)/100
        if op == "+":
            value+=1
        elif op == "-" and value <= 1:
            value=1-value
        else:
            raise ValueError(f"Illegal argument: some What_If_Change items are not well constructed\n{change}")
        return value,"*"

    def update_df(df: pd.DataFrame, kpis: list, changes:list, machine:str):

        #for each pair (kpi,change)
        for kpi,change in zip(kpis,changes):
            # kpi could be in the form 'KPINAME_avg/sum/min/max': in that case KPINAME and the latter part needs to be splitted because we need kpi to be KPINAME
            #default kpi_acc value for everything different from  ["avg","max","min"] is "sum"
            kpi_acc = "sum"
            kpi=kpi.split("_")
            temp=kpi[-1]
            if temp in ["avg","max","min","sum","med","std"]:
                kpi="_".join(kpi[:-1])
            else:
                # The kpi does not include an accumulator at the end
                kpi="_".join(kpi)
            if temp in ["avg","max","min"]:
                kpi_acc = temp
            #change must be converted in a fixed number to be sostituited into the dataframe or to be multiplicated/added to the previous dataframe value
            # TODO: per ora si supporta solo la percentuale
            change, operation = kpi_dataframe_update._parse_change(change)
            if operation == "*":
                print(kpi_acc)
                print(change)
                df.loc[(df["name"] == machine) & (df["kpi"] == kpi), kpi_acc]*= change
            else: 
                raise ValueError(f"Illegal argument: some What_If_Change or What_If_Kpis items are not well constructed\n{changes}")
        return df