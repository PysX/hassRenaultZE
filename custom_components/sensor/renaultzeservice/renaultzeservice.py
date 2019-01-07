"""Support for Renault ZE services."""

import aiohttp
import asyncio
import json
import base64
import time


class RenaultZEService:
    # API Gateway.
    servicesHost = 'https://www.services.renault-ze.com'

    def __init__(self, tokenPath=None):
        """Initialize the sensor."""
        self._tokenData = None
        self._tokenPath = tokenPath

    @property
    def tokenData(self):
        if (self._tokenPath is not None):
            try:
                with open(self._tokenPath, 'r') as tokenStorage:
                    return json.load(tokenStorage)
            except FileNotFoundError:
                return None
        return self._tokenData

    @tokenData.setter
    def tokenData(self, value):
        if (self._tokenPath is not None):
            with open(self._tokenPath, 'w') as outfile:
                json.dump(value, outfile)
                return
        self._tokenData = value

    async def getAccessToken(self, user, password):
        tokenData = self.tokenData
        if tokenData is not None:
            # We could be using python_jwt but even the official ZE Services
            # ("decodeToken") does it this crude way, so why overcomplicate
            # things?
            splitToken = tokenData['token'].split('.')

            # Check it looks semi-valid.
            if len(splitToken) != 3:
                raise ValueError('Not a well formed JWT token')

            # Get the JSON payload of the JWT token.
            b64payload = splitToken[1]
            missing_padding = len(b64payload) % 4
            if missing_padding:
                b64payload += '=' * (4 - missing_padding)
            jsonPayload = base64.b64decode(b64payload)

            # Parse it as JSON.
            token = json.loads(jsonPayload)

            # Is the token still valid? If not, refresh it.
            if(time.gmtime() > time.gmtime(token['exp'])):
                url = RenaultZEService.servicesHost + '/api/user/token/refresh'
                payload = {'token': tokenData['token']}
                headers = {'X-XSRF-TOKEN': tokenData['xsrfToken']}
                cookies = {'refreshToken': tokenData['refreshToken']}

                async with aiohttp.ClientSession(
                        skip_auto_headers=['User-Agent'],
                        cookies=cookies
                        ) as session:
                    async with session.post(
                            url,
                            headers=headers,
                            json=payload
                            ) as response:
                        jsonresponse = await response.json()

                        if jsonresponse.get('token', '') == '':
                            self.tokenData = None
                            return await self.getAccessToken(user, password)

                        # Overwrite the current token with
                        # this newly returned one.
                        tokenData['token'] = jsonresponse['token']

                        # Save this refresh token and new JWT token so we are
                        # nicer to Renault's authentication server.
                        self.tokenData = tokenData

            self.accessToken = tokenData['token']
            # Return the token (as-is if valid, refreshed if not).
            return tokenData['token']

        # We have never cached an access token before.
        else:
            url = RenaultZEService.servicesHost + '/api/user/login'
            payload = {'username': user, 'password': password}
            async with aiohttp.ClientSession(
                    skip_auto_headers=['User-Agent']
                    ) as session:
                async with session.post(url, json=payload) as response:
                    jsonresponse = await response.json()

                    # We do not want to save all the user data returned on
                    # login, so we create a smaller file of just the
                    # mandatory information.
                    tokenData = {
                        'refreshToken': response.cookies['refreshToken'].value,
                        'xsrfToken': jsonresponse['xsrfToken'],
                        'token': jsonresponse['token']
                        }

                    # Save this refresh token and JWT token for future use
                    # so we are nicer to Renault's authentication server.
                    self.tokenData = tokenData

                    self.accessToken = jsonresponse['token']
                    # The script will just want the token.
                    return jsonresponse['token']

    async def apiGetCall(self, path):
        url = RenaultZEService.servicesHost + path
        headers = {'Authorization': 'Bearer ' + self.accessToken}
        async with aiohttp.ClientSession(
                skip_auto_headers=['User-Agent']
                ) as session:
            async with session.get(url, headers=headers) as response:
                return await response.text()

    async def apiPostCall(self, path):
        url = RenaultZEService.servicesHost + path
        headers = {'Authorization': 'Bearer ' + self.accessToken}
        async with aiohttp.ClientSession(
                skip_auto_headers=['User-Agent']
                ) as session:
            async with session.post(url, headers=headers) as response:
                return await response.text()