import { useRouteLoaderData } from "react-router";

export type Role = "boss" | "admin";

export const useRole = () => useRouteLoaderData("root") as Role;
