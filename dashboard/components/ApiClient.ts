import axios from "axios";

const baseURL = process.env.NEXT_PUBLIC_GOVERNOR_API || "http://localhost:8000";

export const api = axios.create({
  baseURL
});
