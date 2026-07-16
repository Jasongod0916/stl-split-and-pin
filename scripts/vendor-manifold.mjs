import { mkdirSync, copyFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const source = join(root, 'node_modules', 'manifold-3d');
const target = join(root, 'third_party', 'manifold');

mkdirSync(target, { recursive: true });
copyFileSync(join(source, 'manifold.js'), join(target, 'manifold.js'));
copyFileSync(join(source, 'manifold.wasm'), join(target, 'manifold.wasm'));
copyFileSync(join(source, 'LICENSE'), join(target, 'LICENSE'));

console.log(`Copied manifold-3d runtime to ${target}`);
