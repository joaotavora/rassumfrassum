const a: string = 2;

async function foo(n: number) {}

async function bar() {
	for (const n of [1, 2, 3]) {
		await foo(n); // this should throw an eslint error: Unexpected `await` inside a loop. But it does not.
	}
}
