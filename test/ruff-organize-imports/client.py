#!/usr/bin/env python3
"""
Test that rass correctly routes ruff.applyOrganizeImports through
workspace/executeCommand when ruff is run standalone via `rass -- ruff server`.
"""

import asyncio

from rassumfrassum.test2 import LspTestEndpoint, log


async def main():
    client = await LspTestEndpoint.create()

    test_project = "/tmp/test-project"
    file_uri = f"file://{test_project}/hello.py"
    file_content = "import os\nimport sys\nimport json\n\ndef hello():\n    print(\"hello\")\n"

    capabilities = {"workspace": {"applyEdit": True}}

    init_response = await client.initialize(
        capabilities=capabilities, rootUri=f"file://{test_project}"
    )

    result = init_response.get("result", {})
    server_caps = result.get("capabilities", {})

    ecp = server_caps.get("executeCommandProvider")
    assert ecp is not None, "Expected executeCommandProvider in capabilities"
    commands = ecp.get("commands", [])
    assert "ruff.applyOrganizeImports" in commands, (
        f"ruff.applyOrganizeImports not found in commands: {commands}"
    )
    log(
        client.name, "executeCommandProvider includes ruff.applyOrganizeImports"
    )

    # Open the document before executing command on it
    await client.notify(
        "textDocument/didOpen",
        {
            "textDocument": {
                "uri": file_uri,
                "version": 1,
                "languageId": "python",
                "text": file_content,
            }
        },
    )
    log(client.name, "Opened document")

    log(
        client.name,
        "Sending workspace/executeCommand ruff.applyOrganizeImports",
    )
    req_id = await client.request(
        "workspace/executeCommand",
        {
            "command": "ruff.applyOrganizeImports",
            "arguments": [{"uri": file_uri, "version": 1}],
        },
    )

    response = await client.read_response(req_id)
    log(client.name, f"Got executeCommand response: {response}")

    assert "result" in response, (
        f"Expected result in executeCommand response, got: {response}"
    )
    assert "error" not in response, (
        f"Expected no error in executeCommand response, got: {response}"
    )

    log(
        client.name,
        "OK! ruff.applyOrganizeImports routed and executed successfully!",
    )

    await client.byebye()


if __name__ == "__main__":
    asyncio.run(main())
