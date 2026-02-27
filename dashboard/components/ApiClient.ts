import axios from "axios";

const baseURL = process.env.NEXT_PUBLIC_GOVERNOR_API;
if (!baseURL) {
  console.warn('NEXT_PUBLIC_GOVERNOR_API is not set; requests may fail');
}

export const api = axios.create({
  baseURL
});
