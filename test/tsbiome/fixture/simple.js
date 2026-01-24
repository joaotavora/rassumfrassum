function greet(name) {
	const message = "Hello, " + name;
	return message;
}

function add(a, b) {
	return a + b;
}

const unused = 42;
var oldStyle = "bad";  // Biome should complain about 'var'

export { greet, add };
