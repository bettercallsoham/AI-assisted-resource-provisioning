import cors from "cors";
import express from "express";
import { api } from "./routes/api.js";

const app = express();
app.use(cors());
app.use(express.json());
app.use("/api", api);
const port = Number(process.env.PORT ?? 3000);
app.listen(port, () => console.log(`Backend listening on ${port}`));