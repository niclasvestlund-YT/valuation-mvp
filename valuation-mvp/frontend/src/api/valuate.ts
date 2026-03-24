import { ValuationResponse } from "../types";

export async function valuateImages(files: File[]): Promise<ValuationResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("images", file);
  }

  const response = await fetch("/api/valuate", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export async function revaluateByName(productName: string): Promise<ValuationResponse> {
  const response = await fetch("/api/revaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_name: productName }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}
