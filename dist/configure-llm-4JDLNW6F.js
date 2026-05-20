import "./chunk-7D4SUZUM.js";

// src/commands/configure-llm.ts
var providerGuides = {
  openrouter: {
    name: "OpenRouter",
    models: ["openrouter/openai/gpt-5.2"],
    requiredEnv: ["OPENROUTER_API_KEY"],
    notes: ["Set AIDD_INTERN_DEFAULT_MODEL_ID to an openrouter/<provider>/<model> id."]
  },
  openai: {
    name: "OpenAI",
    models: ["openai/gpt-5.5"],
    requiredEnv: ["OPENAI_API_KEY"],
    notes: ["Use direct openai/<model> ids when you want OpenAI as the provider."]
  },
  anthropic: {
    name: "Anthropic",
    models: ["anthropic/claude-opus-4-6"],
    requiredEnv: ["ANTHROPIC_API_KEY"],
    notes: ["Use direct anthropic/<model> ids when you want Anthropic as the provider."]
  },
  siliconflow: {
    name: "SiliconFlow",
    models: ["siliconflow/deepseek-ai/DeepSeek-V4-Flash"],
    requiredEnv: ["SILICONFLOW_API_KEY"],
    notes: ["Use siliconflow/<model> ids for the SiliconFlow OpenAI-compatible endpoint."]
  },
  local: {
    name: "Local OpenAI-compatible server",
    models: ["ollama/llama3.1:8b", "vllm/Qwen/Qwen3-Coder-30B-A3B-Instruct", "lm_studio/google/gemma-3-4b", "llamacpp/qwen3.6-35b-a3b-gguf"],
    requiredEnv: ["AIDD_INTERN_DEFAULT_MODEL_ID"],
    optionalEnv: ["LOCAL_LLM_BASE_URL", "LOCAL_LLM_API_KEY", "OLLAMA_BASE_URL", "VLLM_BASE_URL", "LMSTUDIO_BASE_URL", "LLAMACPP_BASE_URL"],
    notes: ["Start the local inference server first; AIDD-Intern does not load model weights itself."]
  }
};
function runConfigureLlm(provider) {
  const normalized = provider?.trim().toLowerCase();
  const guide = normalized ? providerGuides[normalized] : void 0;
  if (normalized && !guide) {
    console.error(`Unknown provider: ${provider}`);
    console.error(`Known providers: ${Object.keys(providerGuides).join(", ")}`);
    return false;
  }
  if (guide) {
    printGuide(guide);
    return true;
  }
  console.log("STEP 1: Choose one provider and model id");
  for (const entry of Object.values(providerGuides)) {
    console.log(`- ${entry.name}: ${entry.models[0]}`);
  }
  console.log("");
  console.log("STEP 2: Add the matching environment variables to .env");
  console.log("Run a provider-specific guide, for example:");
  console.log("  aidd-intern configure-llm openrouter");
  console.log("  aidd-intern configure-llm local");
  console.log("");
  console.log("STEP 3: Verify the runtime side with the Python CLI");
  console.log("  aidd-intern --doctor");
  console.log('  aidd-intern --model openrouter/openai/gpt-5.2 "hello"');
  return true;
}
function printGuide(guide) {
  console.log(`STEP 1: Configure ${guide.name}`);
  console.log("Model examples:");
  for (const model of guide.models) {
    console.log(`  ${model}`);
  }
  console.log("");
  console.log("STEP 2: Set environment variables in .env");
  for (const envName of guide.requiredEnv) {
    console.log(`  ${envName}=...`);
  }
  if (guide.optionalEnv?.length) {
    console.log("Optional:");
    for (const envName of guide.optionalEnv) {
      console.log(`  ${envName}=...`);
    }
  }
  console.log("");
  console.log("STEP 3: Verify");
  console.log(`  AIDD_INTERN_DEFAULT_MODEL_ID=${guide.models[0]}`);
  console.log("  aidd-intern --doctor");
  for (const note of guide.notes) {
    console.log(`Note: ${note}`);
  }
}
export {
  runConfigureLlm
};
//# sourceMappingURL=configure-llm-4JDLNW6F.js.map