import { type RouteConfig, index, route } from "@react-router/dev/routes";
import { documentPages } from "./content/config";
export default [
  route(":lang?", "routes/site.tsx", [
    index("routes/home.tsx"),
    route("releases", "routes/releases.tsx"),
    route("releases/:version", "routes/version.tsx"),
    route("master", "routes/master.tsx"),
    route("master/:year", "routes/year.tsx"),
    route("build/:tag", "routes/build.tsx"),
    ...documentPages.map(([page]) =>
      route(page, "routes/doc.tsx", { id: page }),
    ),
  ]),
] satisfies RouteConfig;
