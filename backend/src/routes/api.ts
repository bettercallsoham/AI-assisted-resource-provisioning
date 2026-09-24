import { Router } from "express";
import { getSnapshot, metrics, events, hosts } from "../services/orchestration.js";

export const api = Router();
api.get("/health", (_request, response) => response.json({ status: "healthy", service: "backend" }));
api.get("/metrics", async (_request, response) => response.json(await metrics()));
api.get("/infrastructure", (_request, response) => response.json({ hosts }));
api.get("/state", async (_request, response) => response.json(await getSnapshot()));
api.get("/prediction", async (_request, response) => response.json((await getSnapshot()).prediction));
api.get("/decision", async (_request, response) => response.json((await getSnapshot()).decision));
api.get("/placement", async (_request, response) => response.json((await getSnapshot()).placement));
api.get("/explanation", async (_request, response) => response.json((await getSnapshot()).explanation));
api.get("/events", (_request, response) => response.json(events));