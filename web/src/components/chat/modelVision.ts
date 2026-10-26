/** Models known to be text-only in the current routing. Sending an image to one
 *  is not blocked; the composer only warns that, without vision/OpenRouter or a
 *  multimodal model, the image stays attached but unanalysed. */
const TEXT_ONLY_MODELS = ["deepseek", "gpt-oss", "glm-5", "glm-4.7", "qwen3-coder", "qwen3-32b", "qwen3-235b", "minimax-m2"];

export function modelLikelyNeedsVisionTool(model: string | null): boolean {
  const normalized = (model ?? "").trim().toLowerCase();
  return !!normalized && TEXT_ONLY_MODELS.some((needle) => normalized.includes(needle));
}
