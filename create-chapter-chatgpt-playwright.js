const path = require('path');

const generatedScript = path.join(__dirname, 'runtime', 'jobs', 'create-chapter-chatgpt-playwright.js');

try {
  require(generatedScript);
} catch (error) {
  console.error(`Generated ChatGPT chapter helper was not found at ${generatedScript}. Start the chapter writer from the app so it can create a job-specific runtime helper.`);
  console.error(error && error.message ? error.message : error);
  process.exit(1);
}
