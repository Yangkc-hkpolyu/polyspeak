// A separate Vue entry; no production PolyInterview services are contacted.
process.env.SPEAKING_ONLY = 'true';
const Service = require('@vue/cli-service');
const command = process.argv[2] === 'serve' ? 'serve' : 'build';
new Service(process.cwd()).run(command, { mode: command === 'serve' ? 'development' : 'production' }).catch(error => {
  console.error(error.message); process.exitCode = 1;
});
