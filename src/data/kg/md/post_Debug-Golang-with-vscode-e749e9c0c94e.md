# Debug Golang with vscode

**Type:** Article
**Tags:** Go

[{'type': 'heading', 'level': 2, 'text': 'Debug Golang with\xa0vscode'}, {'type': 'paragraph', 'html': 'Make&nbsp;.vscode directory in your project.'}, {'type': 'paragraph', 'html': 'Put launch.json file inside the folder.'}, {'type': 'paragraph', 'html': 'and put below json inside the file.'}, {'type': 'paragraph', 'html': 'then press Cntl + F5'}, {'type': 'code', 'lang': 'json', 'code': '{    // Use IntelliSense to learn about possible attributes.    // Hover to view descriptions of\nexisting attributes.    // For more information, visit:\nhttps://go.microsoft.com/fwlink/?linkid=830387    "version": "0.2.0",    "configurations": [\n{            "name": "Launch Package",            "type": "go",            "request": "launch",\n"mode": "auto",            "program": "main.go",            "envFile": "${workspaceFolder}/.env"\n}    ]}'}]
