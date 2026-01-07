"""Custom LSP logic for testing rass-originated requests."""

from rassumfrassum.frassum import LspLogic
from rassumfrassum.json import JSON


class CustomLogic(LspLogic):
    """Custom logic that makes requests to servers independently."""

    async def on_client_notification(self, method: str, params: JSON) -> None:
        """Intercept dummy_client_notif and make a request to the server."""
        await super().on_client_notification(method, params)

        if method == 'dummy_client_notif':
            # Make a request to the primary server
            is_error, response = await self.request_server(
                self.primary, 'dummy_method', {}
            )

            # Verify the response
            if not is_error and response == 42:
                # Send notification back to client
                await self.notify_client('dummy_server_notif', {'value': response})
            else:
                # Send error notification
                await self.notify_client(
                    'dummy_server_notif',
                    {'error': 'Unexpected response', 'is_error': is_error, 'response': response}
                )
