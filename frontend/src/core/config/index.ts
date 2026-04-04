const getBackendBaseURL = () => {
  if (typeof window === "undefined") {
    return process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
  }
  return process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
};

const getAppURL = () => {
  if (typeof window === "undefined") {
    return process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";
  }
  return process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";
};

export { getBackendBaseURL, getAppURL };
