const ok = require('./lib/ok');
const name = process.argv[2];
const plugin = require(name);
const page = import(`./pages/${name}.js`);
const gone = require('./lib/missing');
// eval(commentedOut)
const two = eval('1 + 1');
setTimeout("tick()", 1000);
const add = new Function('a', 'b', 'return a + b');
module.exports = { ok, plugin, page, gone, two, add };
