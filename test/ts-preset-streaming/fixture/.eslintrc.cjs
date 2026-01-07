module.exports = {
	env: { node: true },
	parser: "@typescript-eslint/parser",
	plugins: ["@typescript-eslint"],
	extends: [
		"eslint:recommended",
		"plugin:@typescript-eslint/recommended",
		"plugin:@typescript-eslint/recommended-requiring-type-checking",
	],
	ignorePatterns: [".eslintrc.js", "src/**/*.test.ts", "@types/*"],
	parserOptions: {
		sourceType: "module",
		ecmaFeatures: {
			modules: true,
		},
		project: ["./tsconfig.json"],
	},
	rules: {
		"@typescript-eslint/require-await": 0,
		"no-await-in-loop": 2,
	},
	settings: { jsdoc: { mode: "typescript" } },
};
