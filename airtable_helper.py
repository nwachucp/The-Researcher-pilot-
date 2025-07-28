import os
from airtable import Airtable 

class AirtableLogger:

    def __init__(self, airtable_token, base_id, table_name):
        self.airtable_token = airtable_token
        self.base_id = base_id
        self.table_name = table_name
        self.airtable = self._initialize_airtable_client()

    def _initialize_airtable_client(self):
 
        try:
            return Airtable(self.base_id, self.table_name, api_key=self.airtable_token)
        except Exception as e:
            raise ConnectionError(f"Failed to initialize Airtable client. Check your token, base ID, and table name. Error: {e}")

    def create_record(self, fields):
        
        try:
            record = self.airtable.insert(fields)
            print(f"Successfully logged to Airtable: {fields.get('Title', 'No Title')}")
            return record
        except Exception as e:
            print(f"Error logging to Airtable: {e} for paper: {fields.get('Title', 'No Title')}")
            return None

    def record_exists(self, field_name, field_value):
  
        try:
            records = self.airtable.search_by_value(field_name, field_value)
            return len(records) > 0
        except Exception as e:
            print(f"Error checking for existing record in Airtable: {e}")
            return False