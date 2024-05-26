import logging

def request_set_decorator(success_status_code=200, set_attribute=None, json_key=None):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            response = func(self, *args, **kwargs)
            if response.status_code != success_status_code:
                logging.error(f"HTTP Error: {response.status_code} - {response.text}")
                return []
            json_data = response.json()
            if json_key:
                data_list = json_data.get(json_key, [])
                if set_attribute:
                    setattr(self, set_attribute, data_list)
                return data_list
            return json_data
        return wrapper
    return decorator