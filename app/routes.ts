import { type RouteConfig, index, route } from "@react-router/dev/routes";
export default [
  route(":lang?", "routes/site.tsx", [
    index("routes/home.tsx"),
    route("releases", "routes/releases.tsx"),
    route("releases/:version", "routes/version.tsx"),
    route("master", "routes/master.tsx"),
    route("master/:year", "routes/year.tsx"),
    route("build/:tag", "routes/build.tsx"),
    route("guide", "routes/doc.tsx", { id: "guide" }),
    route("integration", "routes/doc.tsx", { id: "integration" }),
    route("self-build", "routes/doc.tsx", { id: "self-build" }),
    route("packages", "routes/doc.tsx", { id: "packages" }),
    route("licenses", "routes/doc.tsx", { id: "licenses" }),
    route("reference", "routes/doc.tsx", { id: "reference" }),
    route("history", "routes/doc.tsx", { id: "history" }),
  ]),
] satisfies RouteConfig;
