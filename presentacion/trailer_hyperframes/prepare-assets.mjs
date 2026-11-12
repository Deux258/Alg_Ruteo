import {copyFile,access} from 'node:fs/promises';
const root=new URL('./',import.meta.url);
await copyFile(new URL('node_modules/gsap/dist/gsap.min.js',root),new URL('assets/gsap.min.js',root));
await access(new URL('assets/score-original.wav',root));
console.log('GSAP local y música disponibles.');
