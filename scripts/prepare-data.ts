import { validAssetSet } from "../app/domain/assets";
import {
  readFileSync,
  mkdirSync,
  writeFileSync,
  cpSync,
  rmSync,
} from "node:fs";
import { resolve } from "node:path";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { compile } from "json-schema-to-typescript";
import type { CatalogIndex } from "../.generated/index-types";
import type { CatalogShard } from "../.generated/shard-types";

const data = resolve(process.env.CATALOG_DIR ?? "data");
const schema = resolve(process.env.SCHEMA_DIR ?? "schema/v2");
const read = (path: string) => JSON.parse(readFileSync(path, "utf8"));
const indexSchema = read(resolve(schema, "index.schema.json"));
const shardSchema = read(resolve(schema, "shard.schema.json"));
const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const vi = ajv.compile<CatalogIndex>(indexSchema),
  vs = ajv.compile<CatalogShard>(shardSchema);
const index = read(resolve(data, "index.json"));
if (!vi(index)) throw Error("Invalid catalog: " + ajv.errorsText(vi.errors));
const shards: Record<string, CatalogShard> = {};
const tags = new Set<string>();
for (const [kind, ids] of [
  ["releases", index.releases],
  ["master", index.master],
] as const) {
  for (const id of ids) {
    const key = kind + "/" + id;
    const shard = read(resolve(data, key + ".json"));
    if (!vs(shard)) throw Error(key + ": " + ajv.errorsText(vs.errors));
    if ((kind === "releases" ? shard.version : shard.year) !== id)
      throw Error("Shard identity mismatch: " + key);
    if (!shard.releases.length) throw Error("Empty indexed shard: " + key);
    for (const record of shard.releases) {
      if (kind === "master" && Number(record.date.slice(0, 4)) !== id)
        throw Error("Master year mismatch: " + record.tag);
      for (const [key, v] of Object.entries(record.variants)) {
        if (!validAssetSet(v, key.split("-")[2])) {
          throw Error("Invalid asset set: " + record.tag + "/" + key);
        }
        if (v.note && (v.abi || !key.endsWith("-lgpl")))
          throw Error(
            "Invalid historical LGPL notice: " + record.tag + "/" + key,
          );
        if (v.date && v.date > record.date)
          throw Error("Asset date later than publication: " + record.tag);
      }
      if (tags.has(record.tag)) throw Error("Duplicate tag: " + record.tag);
      tags.add(record.tag);
    }
    shards[key] = shard;
  }
}
mkdirSync(".generated", { recursive: true });
writeFileSync(".generated/catalog.json", JSON.stringify({ index, shards }));
writeFileSync(
  ".generated/index-types.ts",
  await compile({ ...indexSchema, title: "CatalogIndex" }, "CatalogIndex", {
    bannerComment: "// Generated from main schema. Do not edit.",
  }),
);
writeFileSync(
  ".generated/shard-types.ts",
  await compile({ ...shardSchema, title: "CatalogShard" }, "CatalogShard", {
    bannerComment: "// Generated from main schema. Do not edit.",
  }),
);
rmSync("public/data", { recursive: true, force: true });
mkdirSync("public/data", { recursive: true });
cpSync(resolve(data, "index.json"), "public/data/index.json");
for (const key of Object.keys(shards)) {
  mkdirSync("public/data/" + key.split("/")[0], { recursive: true });
  cpSync(resolve(data, key + ".json"), "public/data/" + key + ".json");
}
console.log(
  "Validated " +
    tags.size +
    " releases across " +
    Object.keys(shards).length +
    " shards",
);
