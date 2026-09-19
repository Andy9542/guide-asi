# Формы пути, на которых политика обязана держаться: их гоняет `opa test`, и этот
# файл — полный список того, что README перечисляет примерами. Сравнение записано
# как `tools.allow == false`, а не `not tools.allow`: undefined прошло бы второй
# формой молча, и сломанное правило читалось бы как запрет.
package agent.tools_test

import data.agent.tools

deny_paths := [
	".mcp.json",
	".MCP.json",
	"sub/.mcp.json",
	`C:\proj\.mcp.json`,
	`.\.mcp.json`,
	".mcp.json.",
	".mcp.json ",
	"agent/.mcp.json::$DATA",
	".mcp.json\u0000",
	"x\u0001.mcp.json",
	".mcp.json/",
	"a/../.mcp.json",
	"",
]

allow_paths := [
	"src/app.js",
	"X.mcp.json",
	`C:\proj\src\app.js`,
]

test_deny if {
	every p in deny_paths {
		tools.allow == false with input as {"path": p}
	}
}

test_allow if {
	every p in allow_paths {
		tools.allow with input as {"path": p}
	}
}

test_non_string if {
	tools.allow == false with input as {"path": 123}
	tools.allow == false with input as {"path": null}
	tools.allow == false with input as {}
}
