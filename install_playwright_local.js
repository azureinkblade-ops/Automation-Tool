const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const root = __dirname;
const nodeModules = path.join(root, "node_modules");
const packages = ["playwright", "playwright-core"];

async function download(url, target) {
  const response = await fetch(url, { headers: { "User-Agent": "AutomationTool/1.0" } });
  if (!response.ok) {
    throw new Error(`Download failed ${response.status}: ${url}`);
  }
  const bytes = Buffer.from(await response.arrayBuffer());
  fs.writeFileSync(target, bytes);
}

async function installPackage(name) {
  const metadataResponse = await fetch(`https://registry.npmjs.org/${name}/latest`, {
    headers: { "User-Agent": "AutomationTool/1.0" },
  });
  if (!metadataResponse.ok) {
    throw new Error(`Could not fetch metadata for ${name}: ${metadataResponse.status}`);
  }
  const metadata = await metadataResponse.json();
  const destination = path.join(nodeModules, name);
  if (fs.existsSync(path.join(destination, "package.json"))) {
    console.log(`${name} already installed`);
    return;
  }
  fs.mkdirSync(destination, { recursive: true });
  const tarball = path.join(root, `${name}-${metadata.version}.tgz`);
  await download(metadata.dist.tarball, tarball);
  const result = spawnSync("tar", ["-xzf", tarball, "-C", destination, "--strip-components", "1"], {
    stdio: "inherit",
  });
  fs.unlinkSync(tarball);
  if (result.status !== 0) {
    throw new Error(`tar failed for ${name}`);
  }
  console.log(`${name}@${metadata.version} installed`);
}

(async () => {
  fs.mkdirSync(nodeModules, { recursive: true });
  for (const name of packages) {
    await installPackage(name);
  }
})();
