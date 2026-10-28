export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  method: string,
  url: string,
  body?: unknown,
  options?: { signal?: AbortSignal },
): Promise<T> {
  const headers: Record<string, string> = {};
  let processedBody: BodyInit | undefined;

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    processedBody = JSON.stringify(body);
  }

  const res = await fetch(url, {
    method,
    headers,
    body: processedBody,
    credentials: "include",
    signal: options?.signal,
  });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const json = await res.json();
      if (json.errors && Array.isArray(json.errors)) message = json.errors.join("; ");
      else if (json.error) message = json.error;
      else if (json.message) message = json.message;
    } catch {
      // use default statusText
    }
    throw new ApiError(res.status, message);
  }

  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

async function upload<T>(url: string, formData: FormData): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    body: formData,
    credentials: "include",
  });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const json = await res.json();
      if (json.error) message = json.error;
      else if (json.message) message = json.message;
    } catch {
      // use default statusText
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

export const api = {
  get<T>(url: string): Promise<T> {
    return request<T>("GET", url);
  },
  post<T>(url: string, body?: unknown): Promise<T> {
    return request<T>("POST", url, body);
  },
  put<T>(url: string, body?: unknown, options?: { signal?: AbortSignal }): Promise<T> {
    return request<T>("PUT", url, body, options);
  },
  delete<T>(url: string): Promise<T> {
    return request<T>("DELETE", url);
  },
  upload<T>(url: string, formData: FormData): Promise<T> {
    return upload<T>(url, formData);
  },
};
