import os

from dateutil.relativedelta import relativedelta
from itertools import product
from dotenv import load_dotenv
from rdflib import Graph
from datetime import datetime, timedelta
import regex as re

# Load environment variables
load_dotenv()

class QueryGenerator:
    """
    A class to generate from the user input, queries to interact with other modules.

    Every 'private' class method is called only with label == "kpi_calc" or label =="predictions".

    Attributes:
        ERROR_NO_KPIS (int): Error code indicating no KPIs were provided in a user request.
        ERROR_ALL_KPIS (int): Error code indicating all KPIs were requested in a user request.
        llm (object): Language model instance for processing user inputs.
        TODAY (datetime): Reference date.

    Methods:
        _string_to_array(string, type): Parses a string into an array based on KB definitions.
        _check_absolute_time_window(dates, label): Validates a time window and its consistency with the label.
        _kb_update(): Updates the internal state of the KB with machine and KPI data.
        _last_next_days(data, time, days): Calculates the date range for a given number of days.
        _last_next_weeks(data, time, weeks): Calculates the date range for a given number of weeks.
        _last_next_months(data, time, months): Calculates the date range for a given number of months.
        _date_parser(date, label): Parses and validates a date or time window.
        _json_parser(data, label): Converts processed data into a JSON-formatted structure.
        query_generation(input, label): Generates a query based on user input and predefined rules.
    """
    ERROR_NO_MACHINES = "Error: You can't do this type of request without including any machine, try again with at least one machine."
    ERROR_ALL_MACHINES = "Error: You can't do this type of request asking for all machines, try again with less machines."
    ERROR_NO_KPIS = "Error: You can't calculate/predict for no kpis, try again with at least one kpi."
    ERROR_ALL_KPIS = "Error: You can't calculate/predict for all kpis, try again with less kpis."
    ERROR_INVALID_DATE= "Error: Invalid request date format."
    ERROR_NO_CHANGES = "Error: At least one of the user input requests does not contain any valid kpi to be changed."
    ERROR_ALL_CHANGES = "Error: At least one of the user input requests asks for all kpis to be changed, try again with less kpis."
    PROMPTS_PATH = os.path.dirname(os.path.abspath(__file__))+"/prompts/"

    def __init__(self, llm):
        """
        Initializes the QueryGenerator instance.

        Args:
            llm (object): Language model instance for processing user inputs.
        """
        self.llm=llm
        self.calc_pred_prompt=open(self.PROMPTS_PATH+"kpi_calc_pred.txt").read().strip()
        self.report_prompt =open(self.PROMPTS_PATH+"report.txt").read().strip()
        self.what_if_prompt =open(self.PROMPTS_PATH+"what_if.txt").read().strip()

    def _string_to_array(self,string ,type):
        """
        Parses a string into an array of valid KPIs, machines or the special tokens ['ALL'] and ['NULL'].

        There are specific cases where the llm may return kpis or machines which do not belong to the KB.
        Example: 'Assembly machine 6' is not in KB but it may be returned as a match because llm 
        may see it as a typo but because they are equally similar, the model can't disambiguate
        between the different Assembly machines actually in the KB.

        Args:
            string (str): Input string to parse.
            type (str): Type of entities to extract ("machines" or "kpis").

        Returns:
            list: Valid entities from the KB or the special values ['ALL'] or ['NULL'].
        """
        string = string.strip("[]").split(", ")
        array = []
        for x in string:
            x=x.strip("'")
            if (type == "machines" and (x in self.machine_res)) or (type == "kpis" and (x in self.kpi_res)) or x == "ALL" or x == "NULL":
                array.append(x)
        if len(array) == 0:
            return ['NULL']
        return array
    
    def _check_absolute_time_window(self, dates, label):
        """
        Validates with the respect to the userInput classification label, 
        an absolute time window (exact dates, not relative to the current day) for consistency.

        Args:
            dates (list): the array of the two dates of the time window to be checked
            label (str): Classification label ("kpi_calc" or "predictions").

        Returns:
            bool: True if the time window is valid, False otherwise.
        """
        # the time window is 'dates[0] -> dates[1]', check if dates[0] < dates[1] and for some formatting error
        try: 
            start = datetime.strptime(dates[0], "%Y-%m-%d")
            end = datetime.strptime(dates[1], "%Y-%m-%d")
        except:
            return False
        if (end -start).days < 0:
            return False
        """
        Due to the following user case the two delta variables are needed:
        Example: "predict/calculate X for the month of April 2024"
        If TODAY is somewhere in the middle of april, the query generator has to create a query
        which calculate only a fraction of the month.
        """
        delta_p = (end - self.TODAY).days
        delta_k = (start - self.TODAY).days
        if (delta_p > 0 and label == "predictions") or (delta_k < 0 and label == "kpi_calc"):
            return True
        # time window not consistent with label or attempt to calculate/predict for TODAY
        return False

            
    def _search_not_atomics(self, kpis):
        # query the KB for each non atomic kpis whose atomic formula contains at least one kpi from 'kpis'
        not_atomics = []
        for key in self.not_atomic_kpis:
            formula = self.not_atomic_kpis[key]
            #to look for kpi in formula regex can be used
            for kpi in kpis:
                regex = r"\b"+re.escape(kpi)+r"\b"
                if re.search(regex, formula) != None:
                    not_atomics.append(key)
                    break
        return not_atomics


    def _kb_update(self):
        """
        Updates the queryGen instance variables by checkin the current day and querying KB for available machines and KPIs.

        Queries the knowledge base file specified in the environment variables and updates the 'TODAY',
        `machine_res` and `kpi_res` instance variables with valid machine and KPI IDs.
        """
        # actual TODAY
        """
        temp = datetime.now()
        self.TODAY = datetime(year=temp.year,month=temp.month,day=temp.day)
        """
        # demo TODAY
        self.TODAY = datetime(year= 2024,month=10,day=19)
        kpi_query= """
        PREFIX ontology: <http://www.semanticweb.org/raffi/ontologies/2024/10/sa-ontology#>
        SELECT ?id ?formula WHERE {
        ?kpi rdf:type ?type.
        FILTER (?type IN (ontology:ProductionKPI_Production, ontology:EnergyKPI_Consumption, ontology:EnergyKPI_Cost, ontology:MachineUsageKPI, ontology:ProductionKPI_Quality, ontology:CustomKPItmp)).
        ?kpi ontology:id ?id .
        ?kpi ontology:atomic_formula ?formula.
        }
        """
        machine_query="""
        PREFIX ontology: <http://www.semanticweb.org/raffi/ontologies/2024/10/sa-ontology#>
        SELECT ?id WHERE {
        ?machine rdf:type ?type
        FILTER (?type IN (ontology:AssemblyMachine, ontology:LargeCapacityCuttingMachine, ontology:LaserCutter, ontology:LaserWeldingMachine, ontology:LowCapacityCuttingMachine, ontology:MediumCapacityCuttingMachine, ontology:RivetingMachine, ontology:TestingMachine)).
        ?machine ontology:id ?id.
        }
        """
        graph = Graph()
        graph.parse(os.environ['KB_FILE_PATH'] + os.environ['KB_FILE_NAME'], format="xml")
        res = graph.query(kpi_query)
        self.kpi_res = []
        self.not_atomic_kpis = {}
        for row in res:
            self.kpi_res.append(str(row["id"]))
            formula=str(row["formula"])
            if formula != "-":
                self.not_atomic_kpis[str(row["id"])] = formula
        res = graph.query(machine_query)
        self.machine_res = []
        for row in res:
            self.machine_res.append(str(row["id"]))

    def _last_next_days(self,date: datetime,time,days):
        """
        Calculates a time window based on the `time` parameter:
        - If `time` is "last", it returns a time window starting from the ('days')-th day before 'date' to the day before 'date'.
        - If `time` is "next", it returns a time window expressed as the number of days which occurs from the day after 'date' to the ('days')-th day after 'date'.

        Args:
            date (datetime): The reference date.
            time (str): Specifies "last"(kpi engine) for past days or "next"(predictor) for future days.
            days (int): The number of days that have passed/to pass from 'date' to the start/end of the time window.

        Returns:
            tuple: A tuple containing start and end dates as strings if time == "last",
            the integer 'days' if time == "next" or an error message.
        """
        if time == "last":
            start = date - timedelta(days=days)
            end = date - timedelta(days= 1)
            return start.strftime('%Y-%m-%d'),end.strftime('%Y-%m-%d')
        # time == 'next'   
        elif time == "next": 
            return days
        else: 
            return "INVALID DATE"
        
    def _last_next_weeks(self,date: datetime,time,weeks):
        """
        Calculates a time window based on the `time` parameter:
        - If `time` is "last", it returns a time window starting from the first day of the ('weeks')-th past week (with the respect to the week containing 'date')
        to the day before the one containing 'date'.
        - If `time` is "next", it returns a time window expressed as the number of days which occurs from the day after 'date' 
        to the last day of the ('weeks')-th week following the one containing date.

        Args:
            date (datetime): The reference date.
            time (str): Specifies "last"(kpi engine) for past weeks or "next"(predictor) for future weeks.
            weeks (int): The number of weeks that have passed/to pass from 'date' to the start/end of the time window.

        Returns:
            tuple: A tuple containing start and end dates as strings if time == "last",
            the integer which express the number of days which occurs from the day after 'date'
            to the last day of the ('weeks')-th week following the one containing date or
            an error message.
        """
        if time == "last":
            # calculate the day of the week of 'date' (0=Lunedì, 6=Domenica)
            start = date - timedelta(days=(7 * weeks) +date.weekday())
            end = date - timedelta(days= 1 +date.weekday())
            return start.strftime('%Y-%m-%d'),end.strftime('%Y-%m-%d')
        # time == next    
        elif time == "next":
            # 7 - date.weekday() -> monday of the following week
            return (7 - date.weekday()) + 7 * weeks - 1
        else: 
            return "INVALID DATE"
        
    def _last_next_months(self,date,time,months):
        """
        Calculates a time window based on the `time` parameter:
        - If `time` is "last", it returns a time window starting from the first day of the ('months')-th past month (with the respect to the month containing 'date')
        to the last day of the month before the one containing 'date'.
        - If `time` is "next", it returns a time window expressed as the number of days which occurs from the day after 'date' 
        to the last day of the ('months')-th month following the one containing date.

        Args:
            date (datetime): The reference date.
            time (str): Specifies "last"(kpi engine) for past months or "next"(predictor) for future months.
            months (int): The number of months that have passed/to pass from 'date' to the start/end of the time window.

        Returns:
            tuple: A tuple containing start and end dates as strings if time == "last",
            the integer which express the number of days which occurs from the day after 'date' 
            to the last day of the ('months')-th month following the one containing date or
            an error message.
        """
        first_of_the_current_month= date - relativedelta(days= date.day-1)
        if time == "last":
            end_of_the_month = first_of_the_current_month - relativedelta(days=1)
            first_of_the_month = first_of_the_current_month - relativedelta(months= months)
            return first_of_the_month.strftime('%Y-%m-%d') , end_of_the_month.strftime('%Y-%m-%d')
        # time == next    
        elif time == "next":
            first_of_the_month = first_of_the_current_month + relativedelta(months= 1)
            end_of_the_month = first_of_the_month + relativedelta(months= months) - relativedelta(days = 1)
            return (end_of_the_month - date).days
        else: 
            return "INVALID DATE"   
        
    
    def _date_parser(self,date,label):
        """
        Parses and validates a time window based on one retrieved from user input.

        Args:
            date (str): The user-specified time window (retrieved by the llm).
            label (str): The user input classification label, either "kpi_calc" or "predictions".

        Returns:
            tuple or str: A valid time window or "INVALID DATE" if parsing fails.
        """
        if "NULL" in date: 
            # date not provided from the user => default action
            if label == "kpi_calc":
                return self._last_next_days(self.TODAY,"last",30)
            else:
                # predictions
                return self._last_next_days(self.TODAY,"next",30)
        # absolute time window
        if "->" in date:
            temp=date.split(" -> ")
            if not(self._check_absolute_time_window(temp,label)):
                return "INVALID DATE"
            delta= (datetime.strptime(temp[1], "%Y-%m-%d")-self.TODAY).days
            if label == "predictions":
                return delta
            if delta >= 0:
                # the time window is only partially calculable because TODAY is contained in it
                return temp[0], (self.TODAY- relativedelta(days=1)).strftime('%Y-%m-%d')
            return temp[0],temp[1]
        # relative time window
        if "<" in date:
            # date format: <last/next, X, days/weeks/months>
            temp=date.strip("<>").split(", ")
            temp[1]=int(temp[1])
            if (temp[0] == "last" and label != "kpi_calc") or (temp[0] == "next" and label != "predictions") or temp[1] == 0:
                return "INVALID DATE"
            if temp[2] == "days":
                return self._last_next_days(self.TODAY,temp[0],temp[1])
            elif temp[2] == "weeks":
                return self._last_next_weeks(self.TODAY,temp[0],temp[1])
            elif temp[2] == "months":
                return self._last_next_months(self.TODAY,temp[0],temp[1])
        return "INVALID DATE"    
    
    def _json_parser(self, data, label):
        """
        Parses processed LLM output into JSON format to send it to kpi engine or predictor.

        Args:
            data (str): LLM output in the format: OUTPUT: (query1), (query2), (query3)
            label (str): The user input classification label, either "kpi_calc" or "predictions".
        Returns:
            tuple: A JSON-compatible dictionary and an error message (if applicable).
        """
        json_out= []
        error = []
        data = data.replace("OUTPUT: ","")
        data= data.strip("()").split("), (")
        # for each elem in data, a dictionary (json obj) is created
        for elem in data:
            obj={}
            # it is necessary to include ']' to the split because otherwise it would also be included in the strings of the generated array
            elem = elem.split("], ")
            kpis=elem[1]+"]"
            kpis = self._string_to_array(kpis,"kpis")
            # a request is invalid if it misses the kpi field or if the user query mentions 'all' kpis to be calculate/predicted
            # return also an error log expressing the user inability to make a request asking for all kpis (or none)
            if kpis == ["ALL"]:
                error.append(self.ERROR_ALL_KPIS)
                continue
            if kpis == ["NULL"]:
                error.append(self.ERROR_NO_KPIS)
                continue
            date = self._date_parser(elem[2],label)
            # if there is no valid time window, the related json obj is not built
            if date == "INVALID DATE":
                print("INVALID DATE")
                error.append(self.ERROR_INVALID_DATE)
                continue
            # kpi-engine get a time window with variable starting point while predictor starts always from the day next to the current one
            if label == "kpi_calc":
                obj["Date_Start"] = date[0]
                obj["Date_Finish"] = date[1]
            else:
                # predictions
                obj["Date_prediction"] = date

            machines=elem[0]+"]"
            # transform the string containing the array of machines in an array of string
            machines = self._string_to_array(machines,"machines")
            # machines == ["ALL"] and label == "predictions" => machines -: != ["ALL"/"NULL"]
            if machines == ["ALL"] and label == "predictions":
                machines = self.machine_res
            # (machines != ["NULL"/"ALL"]) => complete json generation (standard behaviour)
            if  machines != ["NULL"] and machines != ["ALL"]:                
                for machine, kpi in product(machines,kpis):
                    new_dict=obj.copy()
                    new_dict["Machine_Name"]=machine
                    new_dict["KPI_Name"] = kpi
                    json_out.append(new_dict)
            else:
                # (machines == ["ALL"/"NULL"] and label == "kpi_calc") or (machines == ["NULL"] and label == "predictions") 
                for kpi in kpis:
                    new_dict=obj.copy()
                    new_dict["KPI_Name"] = kpi
                    json_out.append(new_dict)

        if label == "predictions" :
            json_out={"value":json_out}
  
        return json_out, error
    
    def _whatif_json_parser(self, data):
        json_out= []
        error = []
        data = data.replace("OUTPUT: ","")
        data= data.strip("()").split("), (")
        # for each elem in data, a dictionary (json obj) is created
        for elem in data:
            obj={}
            # it is necessary to include ']' to the split because otherwise it would also be included in the strings of the generated array
            elem = elem.split("], ")
            change_kpis= elem[1]
            # out of change_kpis we need to create an array of kpis and an array of changes (expressed as percentages)
            # a what_if request to kpi engine is invalid if the user input does not contain kpi to be changed or requests for all, to be changed
            if ("NULL" in change_kpis):
                error.append(self.ERROR_NO_CHANGES)
                continue
            if  ("ALL" in change_kpis):
                error.append(self.ERROR_ALL_CHANGES)
            temp_change_kpis=change_kpis.strip("[").split(">, ")
            changes = []
            change_kpis = []
            for _elem in temp_change_kpis:
                _elem=_elem.strip("<>").split(", ")
                _elem[0]=_elem[0].strip("'")
                # check for the existence of the kpi _elem[0] in KB and for the correct percentage change format(+/-(NUMBERS)%) for _elem[1]
                regex=r"([+-])([0-9]+)(\.[0-9]+)?%"
                if _elem[0] in self.kpi_res and (re.search(regex,_elem[1]) != None):
                    change_kpis.append(_elem[0])
                    changes.append(_elem[1])
            # a what_if request to kpi engine is invalid if it misses the what_if_kpi field.
            if len(changes) == 0:
                error.append(self.ERROR_NO_CHANGES)
                continue
            obj["What_If_Change"]=changes
            obj["What_If_KPI"] = change_kpis
            kpis= elem[2]+"]"
            kpis = self._string_to_array(kpis,"kpis")
            # kpis == ["NULL"] or kpis == ["ALL"] -> kpis has to be filled with all kpis which contain at least one kpi of change_kpis
            if kpis == ["NULL"] or kpis == ["ALL"]:
                kpis=self._search_not_atomics(change_kpis)
            else:
                #check if there are kpis in 'kpis' whose atomic formula do not contain any kpi in 'change_kpis'
                temp= []
                for kpi in kpis:
                    if kpi in self.not_atomic_kpis:
                        formula = self.not_atomic_kpis[kpi]
                        for change_kpi in change_kpis:  
                            regex = r"\b"+re.escape(change_kpi)+r"\b"            
                            if re.search(regex, formula) != None:
                                temp.append(kpi)
                                break
                kpis=temp
            # date parsing is the same use cases as kpi_calc
            date = self._date_parser(elem[3], "kpi_calc")
            # if there is no valid time window, the related json obj is not built
            if date == "INVALID DATE":
                print("INVALID DATE")
                error.append(self.ERROR_INVALID_DATE)
                continue
            obj["Date_Start"] = date[0]
            obj["Date_Finish"] = date[1]
            machines=elem[0]+"]"
            machines = self._string_to_array(machines,"machines")
            # a what_if request to kpi engine is invalid if the user input does not contain machine names or it request for all of them
            # (machines != ["NULL"/"ALL"]) => complete json generation (standard behaviour)
            if  machines != ["NULL"] and machines != ["ALL"]:                
                for machine, kpi in product(machines,kpis):
                    new_dict=obj.copy()
                    new_dict["Machine_Name"]=machine
                    new_dict["KPI_Name"] = kpi
                    json_out.append(new_dict)
            elif machines == ["ALL"]:
                error.append(self.ERROR_ALL_MACHINES)
                continue
            else:
                # machines == ["NULL"]
                error.append(self.ERROR_NO_MACHINES)
                continue
  
        return json_out, error


    def query_generation(self,input= "predict idle time max, cost wrking sum and good cycles min for last week for all the medium capacity cutting machine, predict the same kpis for Laser welding machines 2 for today. calculate the cnsumption_min for next 4 month and for Laser cutter the offline time sum for last 23 day. "
, label="kpi_calc"):
        """
        Generates a json query for calculating and predicting KPIs for machines based on user input.
        
        This method processes the user input: an llm matches machine and KPI identifiers from the KB and retrieve from the input
        usefull data to generate a formatted query that can be used as a request to the predictor and kpi engine.

        Arguments:
            - input (str): The user input
            - label (str): The user input classification label, either "kpi_calc", "predictions", "report" or "what_if".

        Returns:
            - A tuple containing two elements:
                1. If the label is 'report', a list with two dictionaries representing the json parsed results based on the user input.
                2. If the label is 'kpi_calc' or 'predictions', a single dictionary representing the json parsed result based on the user input.
        """
        # we should make input as a raw data readable string,doing that % are read as a char and not as a placeholder or something else
        input=r""+input
        self._kb_update()
        YESTERDAY_TW = f"{(self.TODAY-relativedelta(days=1)).strftime('%Y-%m-%d')} -> {(self.TODAY-relativedelta(days=1)).strftime('%Y-%m-%d')}"
        label_handler = {
            "kpi_calc": self.calc_pred_prompt,
            "predictions": self.calc_pred_prompt,
            "report": self.report_prompt,
            "what_if": self.what_if_prompt
        }
        query=label_handler[label]
        if label in ["kpi_calc", "predictions", "report"]:
            TODAY_TW =f"{(self.TODAY).strftime('%Y-%m-%d')} -> {(self.TODAY).strftime('%Y-%m-%d')}"
            TOMORROW_TW=f"{(self.TODAY+relativedelta(days=1)).strftime('%Y-%m-%d')} -> {(self.TODAY+relativedelta(days=1)).strftime('%Y-%m-%d')}"
            TW1 = f"{(self.TODAY + relativedelta(days=5)).strftime('%d/%m/%Y')} -> {(self.TODAY + relativedelta(days=13)).strftime('%d/%m/%Y')}"
            TW2 = f"{(self.TODAY + relativedelta(days=5)).strftime('%Y-%m-%d')} -> {(self.TODAY + relativedelta(days=13)).strftime('%Y-%m-%d')}"
            query= query.format(
                _INPUT_ = input,
                _TODAY_ = self.TODAY,
                _MACHINES_ = self.machine_res,
                _KPIS_ = self.kpi_res,
                _TODAY_TW_ = TODAY_TW,
                _TOMORROW_TW_ = TOMORROW_TW,
                _YESTERDAY_TW_= YESTERDAY_TW,
                _TW1_= TW1,
                _TW2_ = TW2
                )
        else:
            # what_if use case
            query=query.format(
                _INPUT_ = input,
                _TODAY_ = self.TODAY,
                _MACHINES_ = self.machine_res,
                _KPIS_ = self.kpi_res,
                _YESTERDAY_TW_= YESTERDAY_TW,
                )

        data = self.llm.invoke(query)
        data = data.content.strip("\n")
        print(data)
        if label == "what_if":
            json_obj, error = self._whatif_json_parser(data)
            print(f"ERRORS = {error}")
            print("\n")
            print(json_obj)
            return json_obj,error
        elif label == "report":
            # data needs to be splitted in order to make two _json_parser calls
            data_pred= "OUTPUT: "
            data_kpi_calc= "OUTPUT: "
            data = data.replace("OUTPUT: ","")
            data= data.strip("()").split("), (")
            # for each elem in data, a dictionary (json obj) is created
            for elem in data:
                # it is necessary to include ']' to the split because otherwise it would also be included in the strings of the generated array
                elem = elem.split("], ")
                kpis=elem[1]+"]"
                machines=elem[0]+"]"
                # remove the first and last character of the pattern <tw_kpi_calc, tw_prediction>
                elem[2]=elem[2][1:-1]
                dates = elem[2].split("; ")
                tw_prediction = dates[1]
                tw_kpi_calc= dates[0]
                data_pred+=f"({machines}, {kpis}, {tw_prediction}), "
                data_kpi_calc+=f"({machines}, {kpis}, {tw_kpi_calc}), "
            data_kpi_calc=data_kpi_calc.strip(" ,")
            data_pred = data_pred.strip(" ,")
            kpi_json_obj, error = self._json_parser(data_kpi_calc,"kpi_calc")
            pred_json_obj, error = self._json_parser(data_pred,"predictions")
            print("\n")
            print(kpi_json_obj)
            print(pred_json_obj)
            return [kpi_json_obj,pred_json_obj], error
        else:
            json_obj, error = self._json_parser(data,label)
            print("\n")
            print(json_obj)
            return json_obj,error
        
        
        

        
    