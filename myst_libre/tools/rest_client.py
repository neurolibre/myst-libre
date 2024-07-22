"""
rest_client.py

This module contains the RestClient class for making REST API calls.
"""

import requests
from requests.auth import HTTPBasicAuth
from .authenticator import Authenticator

class RestClient(Authenticator):
    """
    RestClient

    A client for making REST API calls.
    
    Args:
        auth (dict): Authentication credentials.
    """
    def __init__(self,dotenvloc = '.'):
        print(dotenvloc)
        super().__init__(dotenvloc)
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(self._auth['username'], self._auth['password'])

    def get(self, url):
        """
        Perform a GET request.
        
        Args:
            url (str): URL for the GET request.
        
        Returns:
            Response: HTTP response object.
        """
        response = self.session.get(url)
        return response

    def post(self, url, data=None, json=None):
        """
        Perform a POST request.
        
        Args:
            url (str): URL for the POST request.
            data (dict, optional): Data to send in the request body.
            json (dict, optional): JSON data to send in the request body.
        
        Returns:
            Response: HTTP response object.
        """
        response = self.session.post(url, data=data, json=json)
        return response