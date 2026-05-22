use pyo3::prelude::*;
use pyo3::exceptions::{PyIOError, PyValueError};
use pyo3::types::{PyDict, PyList, PyTuple};

use std::io::Write;
use std::path::Path;

use md5::{Md5, Digest};
use once_cell::sync::Lazy;
use regex::Regex;
use serde_json::Value;
use tempfile::NamedTempFile;

// ═══════════════════════════════════════════════════════════════════════
// Pre-compiled regex patterns for secret redaction
// ═══════════════════════════════════════════════════════════════════════

static RE_HF_TOKEN: Lazy<Regex> = Lazy::new(|| Regex::new(r"hf_[A-Za-z0-9]{30,}").unwrap());
static RE_ANTHROPIC: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"sk-ant-[A-Za-z0-9_\-]{20,}").unwrap());
// NOTE: The Rust `regex` crate does NOT support lookaheads.
// RE_ANTHROPIC is applied *before* RE_OPENAI in REDACT_PATTERNS, so any
// `sk-ant-…` keys are already replaced by the time RE_OPENAI runs.
// We simply match all `sk-` keys here — the ordering guarantees correctness.
static RE_OPENAI: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"sk-[A-Za-z0-9_\-]{40,}").unwrap());
static RE_GITHUB_CLASSIC: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"gh[pousr]_[A-Za-z0-9]{36,}").unwrap());
static RE_GITHUB_FINE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"github_pat_[A-Za-z0-9_]{36,}").unwrap());
static RE_AWS_KEY: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b").unwrap());
static RE_BEARER: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?i)bearer\s+[A-Za-z0-9_\-\.=]{20,}").unwrap());
static RE_SECRET_NAMES: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r#"(?i)\b(HF_TOKEN|HUGGINGFACEHUB_API_TOKEN|ANTHROPIC_API_KEY|OPENAI_API_KEY|GITHUB_TOKEN|AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|PASSWORD|SECRET|API_KEY)\s*[:=]\s*([^\s"']+)"#,
    )
    .unwrap()
});

struct RedactPattern {
    regex: &'static Lazy<Regex>,
    replacement: &'static str,
}

static REDACT_PATTERNS: &[RedactPattern] = &[
    RedactPattern { regex: &RE_HF_TOKEN, replacement: "[REDACTED_HF_TOKEN]" },
    RedactPattern { regex: &RE_ANTHROPIC, replacement: "[REDACTED_ANTHROPIC_KEY]" },
    RedactPattern { regex: &RE_OPENAI, replacement: "[REDACTED_OPENAI_KEY]" },
    RedactPattern { regex: &RE_GITHUB_CLASSIC, replacement: "[REDACTED_GITHUB_TOKEN]" },
    RedactPattern { regex: &RE_GITHUB_FINE, replacement: "[REDACTED_GITHUB_TOKEN]" },
    RedactPattern { regex: &RE_AWS_KEY, replacement: "[REDACTED_AWS_KEY_ID]" },
    RedactPattern { regex: &RE_BEARER, replacement: "Bearer [REDACTED]" },
];

// ═══════════════════════════════════════════════════════════════════════
// File I/O  (existing save_json_atomic)
// ═══════════════════════════════════════════════════════════════════════

/// Atomically saves bytes to a path via a temporary file + rename.
/// Releases the Python GIL during I/O operations.
#[pyfunction]
fn save_json_atomic(py: Python<'_>, path: &str, content: &[u8]) -> PyResult<()> {
    py.allow_threads(|| -> PyResult<()> {
        let target_path = Path::new(path);

        if let Some(parent) = target_path.parent() {
            if !parent.exists() {
                std::fs::create_dir_all(parent)
                    .map_err(|e| PyIOError::new_err(format!("Failed to create directories: {e}")))?;
            }
        }

        let parent_dir = target_path.parent().unwrap_or_else(|| Path::new("."));
        let mut temp_file = NamedTempFile::new_in(parent_dir)
            .map_err(|e| PyIOError::new_err(format!("Failed to create temporary file: {e}")))?;

        temp_file
            .write_all(content)
            .map_err(|e| PyIOError::new_err(format!("Failed to write to temporary file: {e}")))?;
        temp_file
            .flush()
            .map_err(|e| PyIOError::new_err(format!("Failed to flush temporary file: {e}")))?;
        temp_file
            .persist(target_path)
            .map_err(|e| PyIOError::new_err(format!("Failed to atomically replace target file: {e}")))?;

        Ok(())
    })
}

// ═══════════════════════════════════════════════════════════════════════
// JSON normalisation + hashing  (for doom_loop.py)
// ═══════════════════════════════════════════════════════════════════════

/// Canonicalise a JSON arguments string (sort keys, compact separators)
/// and return the first 12 hex characters of its MD5 digest.
///
/// Falls back to hashing the raw input bytes when the string is not valid
/// JSON, mirroring the Python implementation in ``doom_loop.py``.
#[pyfunction]
fn normalize_and_hash_args(py: Python<'_>, args_str: &str) -> PyResult<String> {
    py.allow_threads(|| {
        let normalized = if args_str.is_empty() {
            String::new()
        } else {
            match serde_json::from_str::<Value>(args_str) {
                Ok(value) => {
                    let sorted = sort_json_value(value);
                    serde_json::to_string(&sorted).unwrap_or_else(|_| args_str.to_string())
                }
                Err(_) => args_str.to_string(),
            }
        };

        let mut hasher = Md5::new();
        hasher.update(normalized.as_bytes());
        let digest = hasher.finalize();
        Ok(format!("{digest:x}")[..12].to_string())
    })
}

// ═══════════════════════════════════════════════════════════════════════
// Secret redaction  (for redact.py)
// ═══════════════════════════════════════════════════════════════════════

/// Apply all redaction patterns to a single string.
#[pyfunction]
fn scrub_string(py: Python<'_>, s: &str) -> PyResult<String> {
    py.allow_threads(|| Ok(apply_scrub_string(s)))
}

/// Recursively scrub every string value in a Python object (dict / list / str).
///
/// Returns a **new** object — the input is not mutated.
#[pyfunction]
fn scrub_obj(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<PyObject> {
    scrub_py_any(py, obj)
}

// ═══════════════════════════════════════════════════════════════════════
// JSON utilities  (for session.py, session_uploader.py)
// ═══════════════════════════════════════════════════════════════════════

/// Serialise a Python object to a JSON string with sorted keys and
/// ``ensure_ascii=False`` semantics (non-ASCII characters are preserved).
#[pyfunction]
fn json_dumps_sorted(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<String> {
    // Convert Python → serde_json::Value while we still hold the GIL
    let value = py_any_to_value(py, obj)?;
    // Sorting + serialisation are pure Rust — safe without the GIL
    py.allow_threads(|| {
        let sorted = sort_json_value(value);
        serde_json::to_string(&sorted)
            .map_err(|e| PyValueError::new_err(format!("JSON serialisation failed: {e}")))
    })
}

/// Serialise a Python object to canonical (sorted, compact) JSON bytes
/// suitable for hashing.
#[pyfunction]
fn json_canonical_bytes(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Vec<u8>> {
    let value = py_any_to_value(py, obj)?;
    py.allow_threads(|| {
        let sorted = sort_json_value(value);
        serde_json::to_vec(&sorted)
            .map_err(|e| PyValueError::new_err(format!("JSON serialisation failed: {e}")))
    })
}

/// Read an entire file as a UTF-8 string.  Releases the GIL during I/O.
#[pyfunction]
fn read_file_utf8(py: Python<'_>, path: &str) -> PyResult<String> {
    py.allow_threads(|| {
        std::fs::read_to_string(path)
            .map_err(|e| PyIOError::new_err(format!("Failed to read file '{path}': {e}")))
    })
}

// ═══════════════════════════════════════════════════════════════════════
// ANSI-aware string processing  (for terminal_display.py)
// ═══════════════════════════════════════════════════════════════════════

/// Truncate *s* to *max_width* visible columns while preserving ANSI escape
/// sequences.  Appends ``\u{2026}`` (ellipsis) when truncation occurs.
#[pyfunction]
fn clip_ansi_string(py: Python<'_>, s: &str, max_width: usize) -> PyResult<String> {
    py.allow_threads(|| Ok(clip_ansi_impl(s, max_width)))
}

/// Return the visible display width of *s*, ignoring ANSI escape sequences
/// and accounting for wide (CJK) characters via ``unicode-width``.
#[pyfunction]
fn visible_width(py: Python<'_>, s: &str) -> PyResult<usize> {
    py.allow_threads(|| Ok(visible_width_impl(s)))
}

// ═══════════════════════════════════════════════════════════════════════
// Doom-loop detection (for doom_loop.py)
// ═══════════════════════════════════════════════════════════════════════

#[derive(Clone, PartialEq, Eq, Debug)]
struct ToolCallSignature {
    name: String,
    args_hash: String,
    result_hash: Option<String>,
}

fn hash_args_rust(args_str: &str) -> String {
    if args_str.is_empty() {
        return String::new();
    }
    let normalized = match serde_json::from_str::<Value>(args_str) {
        Ok(value) => {
            let sorted = sort_json_value(value);
            serde_json::to_string(&sorted).unwrap_or_else(|_| args_str.to_string())
        }
        Err(_) => args_str.to_string(),
    };
    let mut hasher = Md5::new();
    hasher.update(normalized.as_bytes());
    let digest = hasher.finalize();
    format!("{digest:x}")[..12].to_string()
}

/// Detect repeating patterns and consecutive tool calls natively, releasing GIL.
#[pyfunction]
fn detect_doom_loop_rust(
    py: Python<'_>,
    signatures_py: Vec<(String, String, Option<String>)>,
    threshold: usize,
) -> PyResult<Option<(String, String)>> {
    py.allow_threads(|| {
        let signatures: Vec<ToolCallSignature> = signatures_py
            .into_iter()
            .map(|(name, args, res)| {
                let args_hash = hash_args_rust(&args);
                let result_hash = res.map(|r| hash_args_rust(&r));
                ToolCallSignature {
                    name,
                    args_hash,
                    result_hash,
                }
            })
            .collect();

        if signatures.len() < 3 {
            return Ok(None);
        }

        // 1. Check for identical consecutive calls
        let mut consecutive_count = 1;
        for i in 1..signatures.len() {
            if signatures[i] == signatures[i - 1] {
                consecutive_count += 1;
                if consecutive_count >= threshold {
                    return Ok(Some(("consecutive".to_string(), signatures[i].name.clone())));
                }
            } else {
                consecutive_count = 1;
            }
        }

        // 2. Check for repeating sequences (sequences of length 2-5 with 2+ reps)
        let n = signatures.len();
        for seq_len in 2..=5 {
            let min_required = seq_len * 2;
            if n < min_required {
                continue;
            }

            // Check the tail of the signatures list
            let pattern = &signatures[n - min_required..n - min_required + seq_len];

            // Count how many full repetitions from the end
            let mut reps = 0;
            let mut i_pos = n - seq_len;
            loop {
                let chunk = &signatures[i_pos..i_pos + seq_len];
                if chunk == pattern {
                    reps += 1;
                    if i_pos >= seq_len {
                        i_pos -= seq_len;
                    } else {
                        break;
                    }
                } else {
                    break;
                }
            }

            if reps >= 2 {
                let pattern_desc = pattern
                    .iter()
                    .map(|s| s.name.clone())
                    .collect::<Vec<String>>()
                    .join(" → ");
                return Ok(Some(("sequence".to_string(), pattern_desc)));
            }
        }

        Ok(None)
    })
}

// ═══════════════════════════════════════════════════════════════════════
// Internal helpers — JSON
// ═══════════════════════════════════════════════════════════════════════

fn sort_json_value(value: Value) -> Value {
    match value {
        Value::Object(map) => {
            let sorted: serde_json::Map<String, Value> = map
                .into_iter()
                .map(|(k, v)| (k, sort_json_value(v)))
                .collect();
            Value::Object(sorted)
        }
        Value::Array(arr) => Value::Array(arr.into_iter().map(sort_json_value).collect()),
        other => other,
    }
}

fn py_any_to_value(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    if obj.is_none() {
        return Ok(Value::Null);
    }
    if let Ok(b) = obj.extract::<bool>() {
        return Ok(Value::Bool(b));
    }
    if let Ok(i) = obj.extract::<i64>() {
        return Ok(Value::Number(i.into()));
    }
    if let Ok(f) = obj.extract::<f64>() {
        return serde_json::Number::from_f64(f)
            .map(Value::Number)
            .ok_or_else(|| PyValueError::new_err("NaN/Infinity not supported in JSON"));
    }
    if let Ok(s) = obj.extract::<String>() {
        return Ok(Value::String(s));
    }
    if let Ok(dict) = obj.downcast::<PyDict>() {
        let mut map = serde_json::Map::with_capacity(dict.len());
        for (k, v) in dict.iter() {
            let key: String = k.extract()?;
            map.insert(key, py_any_to_value(py, &v)?);
        }
        return Ok(Value::Object(map));
    }
    if let Ok(list) = obj.downcast::<PyList>() {
        let arr: PyResult<Vec<Value>> = list
            .iter()
            .map(|item| py_any_to_value(py, &item))
            .collect();
        return Ok(Value::Array(arr?));
    }
    if let Ok(tuple) = obj.downcast::<PyTuple>() {
        let arr: PyResult<Vec<Value>> = tuple
            .iter()
            .map(|item| py_any_to_value(py, &item))
            .collect();
        return Ok(Value::Array(arr?));
    }
    // Fallback — repr
    Ok(Value::String(obj.repr()?.to_string()))
}

// ═══════════════════════════════════════════════════════════════════════
// Internal helpers — redaction
// ═══════════════════════════════════════════════════════════════════════

fn apply_scrub_string(s: &str) -> String {
    if s.is_empty() {
        return String::new();
    }
    let mut out = s.to_string();
    for pat in REDACT_PATTERNS {
        out = pat.regex.replace_all(&out, pat.replacement).into_owned();
    }
    out = RE_SECRET_NAMES
        .replace_all(&out, "$1=[REDACTED]")
        .into_owned();
    out
}

fn scrub_py_any(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<PyObject> {
    if let Ok(s) = obj.extract::<String>() {
        return Ok(apply_scrub_string(&s).into_pyobject(py)?.into_any().unbind());
    }
    if let Ok(dict) = obj.downcast::<PyDict>() {
        let new_dict = PyDict::new(py);
        for (k, v) in dict.iter() {
            let key_str: String = k.extract()?;
            let scrubbed_v = scrub_py_any(py, &v)?;
            new_dict.set_item(key_str, scrubbed_v)?;
        }
        return Ok(new_dict.into_pyobject(py)?.into_any().unbind());
    }
    if let Ok(list) = obj.downcast::<PyList>() {
        let items: Vec<PyObject> = list
            .iter()
            .map(|item| scrub_py_any(py, &item))
            .collect::<PyResult<Vec<_>>>()?;
        return Ok(PyList::new(py, &items)?.into_pyobject(py)?.into_any().unbind());
    }
    if let Ok(tuple) = obj.downcast::<PyTuple>() {
        let items: Vec<PyObject> = tuple
            .iter()
            .map(|item| scrub_py_any(py, &item))
            .collect::<PyResult<Vec<_>>>()?;
        return Ok(PyTuple::new(py, &items)?.into_pyobject(py)?.into_any().unbind());
    }
    // Non-string scalars pass through unchanged
    Ok(obj.clone().unbind())
}

// ═══════════════════════════════════════════════════════════════════════
// Internal helpers — ANSI
// ═══════════════════════════════════════════════════════════════════════

fn clip_ansi_impl(s: &str, max_width: usize) -> String {
    if max_width == 0 || s.is_empty() {
        return s.to_string();
    }
    let mut out = String::with_capacity(s.len());
    let mut visible: usize = 0;
    let limit = max_width.saturating_sub(1); // reserve 1 col for ellipsis
    let mut truncated = false;
    let mut chars = s.chars().peekable();
    let mut in_ansi = false;

    while let Some(ch) = chars.next() {
        if in_ansi {
            out.push(ch);
            if ch.is_ascii_alphabetic() {
                in_ansi = false;
            }
            continue;
        }
        if ch == '\x1b' {
            in_ansi = true;
            out.push(ch);
            continue;
        }
        let cw = unicode_width::UnicodeWidthChar::width(ch).unwrap_or(0);
        if visible + cw > limit {
            truncated = true;
            break;
        }
        out.push(ch);
        visible += cw;
    }
    if truncated {
        out.push_str("\x1b[0m\u{2026}");
    }
    out
}

fn visible_width_impl(s: &str) -> usize {
    let mut width: usize = 0;
    let mut in_ansi = false;
    for ch in s.chars() {
        if in_ansi {
            if ch.is_ascii_alphabetic() {
                in_ansi = false;
            }
            continue;
        }
        if ch == '\x1b' {
            in_ansi = true;
            continue;
        }
        width += unicode_width::UnicodeWidthChar::width(ch).unwrap_or(0);
    }
    width
}

// ═══════════════════════════════════════════════════════════════════════
// Value to Python converter
// ═══════════════════════════════════════════════════════════════════════

fn value_to_py_any(py: Python<'_>, value: &Value) -> PyResult<PyObject> {
    match value {
        Value::Null => Ok(py.None()),
        Value::Bool(b) => Ok((*b).into_pyobject(py)?.to_owned().into_any().unbind()),
        Value::Number(num) => {
            if let Some(i) = num.as_i64() {
                Ok(i.into_pyobject(py)?.into_any().unbind())
            } else if let Some(f) = num.as_f64() {
                Ok(f.into_pyobject(py)?.into_any().unbind())
            } else {
                Ok(py.None())
            }
        }
        Value::String(s) => Ok(s.as_str().into_pyobject(py)?.into_any().unbind()),
        Value::Array(arr) => {
            let list = PyList::empty(py);
            for item in arr {
                list.append(value_to_py_any(py, item)?)?;
            }
            Ok(list.into_any().unbind())
        }
        Value::Object(map) => {
            let dict = PyDict::new(py);
            for (k, v) in map {
                dict.set_item(k, value_to_py_any(py, v)?)?;
            }
            Ok(dict.into_any().unbind())
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════
// Layered memories formatting (TencentDB-Agent-Memory L3 User Profile generator)
// ═══════════════════════════════════════════════════════════════════════

#[pyfunction]
#[pyo3(signature = (retrieval_res, user_name=None))]
fn format_layered_memories_rust(
    py: Python<'_>,
    retrieval_res: &Bound<'_, PyAny>,
    user_name: Option<String>,
) -> PyResult<PyObject> {
    let value = py_any_to_value(py, retrieval_res)?;

    let res_json = py.allow_threads(|| -> PyResult<Value> {
        let user_label = user_name.as_deref().unwrap_or("User");

        // 1. Extract L1 (Atomic Memory) from retrieve items
        let mut l1_atomic = Vec::new();
        if let Some(items) = value.get("items").and_then(|i| i.as_array()) {
            for item in items {
                let mtype = item.get("memory_type").and_then(|t| t.as_str()).unwrap_or("fact");
                let content = item.get("content").and_then(|c| c.as_str()).unwrap_or("");
                if !content.is_empty() {
                    l1_atomic.push(serde_json::json!({
                        "type": mtype,
                        "content": content
                    }));
                }
            }
        }

        // 2. Extract L2 (Scenario Blocks) from retrieve categories
        let mut l2_scenarios = serde_json::Map::new();
        if let Some(categories) = value.get("categories").and_then(|c| c.as_array()) {
            for cat in categories {
                let name = cat.get("name").and_then(|n| n.as_str()).unwrap_or("general");
                let desc = cat.get("description").and_then(|d| d.as_str()).unwrap_or("");
                let summary = cat.get("summary").and_then(|s| s.as_str()).unwrap_or("");
                l2_scenarios.insert(name.to_string(), serde_json::json!({
                    "description": desc,
                    "summary": summary
                }));
            }
        }

        // 3. Construct L3 (User Profile) by combining atomic preferences and scenario summaries
        let mut l3_lines = Vec::new();
        l3_lines.push(format!("# {} Profile & Persona", user_label));

        // Prefs
        let mut prefs = Vec::new();
        for it in &l1_atomic {
            if let Some(t) = it.get("type").and_then(|t| t.as_str()) {
                if t == "preference" || t == "habit" {
                    if let Some(c) = it.get("content").and_then(|c| c.as_str()) {
                        prefs.push(c);
                    }
                }
            }
        }

        if !prefs.is_empty() {
            l3_lines.push("## Personal Preferences & Habits".to_string());
            for pref in prefs {
                l3_lines.push(format!("- {}", pref));
            }
        } else {
            l3_lines.push("## Personal Preferences & Habits\n*(No recorded preferences)*".to_string());
        }

        // Constraints
        let mut constraints = Vec::new();
        for it in &l1_atomic {
            if let Some(t) = it.get("type").and_then(|t| t.as_str()) {
                if t == "constraint" {
                    if let Some(c) = it.get("content").and_then(|c| c.as_str()) {
                        constraints.push(c);
                    }
                }
            }
        }

        if !constraints.is_empty() {
            l3_lines.push("## Operational Constraints".to_string());
            for const_str in constraints {
                l3_lines.push(format!("- {}", const_str));
            }
        }

        // Summaries of categories
        if !l2_scenarios.is_empty() {
            l3_lines.push("## Scenario Summaries".to_string());
            if let Some(categories) = value.get("categories").and_then(|c| c.as_array()) {
                for cat in categories {
                    let name = cat.get("name").and_then(|n| n.as_str()).unwrap_or("general");
                    if let Some(details) = l2_scenarios.get(name) {
                        let summary = details.get("summary").and_then(|s| s.as_str()).unwrap_or("");
                        l3_lines.push(format!("### Category: {}", name));
                        l3_lines.push(summary.to_string());
                    }
                }
            }
        }

        let l3_profile = l3_lines.join("\n");

        // 4. Render the beautiful, structured 4-tier prompt block
        let mut prompt_blocks = Vec::new();
        prompt_blocks.push("==================================================".to_string());
        prompt_blocks.push("🧠 LAYERED LONG-TERM MEMORY ENGINE (TencentDB-Agent-Memory Schema)".to_string());
        prompt_blocks.push("==================================================".to_string());

        prompt_blocks.push("\n[L3: USER PROFILE & PERSONA]".to_string());
        prompt_blocks.push(l3_profile.clone());

        prompt_blocks.push("\n[L2: ACTIVE SCENARIO BLOCKS]".to_string());
        if !l2_scenarios.is_empty() {
            if let Some(categories) = value.get("categories").and_then(|c| c.as_array()) {
                for cat in categories {
                    let name = cat.get("name").and_then(|n| n.as_str()).unwrap_or("general");
                    if let Some(details) = l2_scenarios.get(name) {
                        let desc = details.get("description").and_then(|d| d.as_str()).unwrap_or("");
                        let summary = details.get("summary").and_then(|s| s.as_str()).unwrap_or("");
                        prompt_blocks.push(format!("### Scenario [{}]: {}", name, desc));
                        prompt_blocks.push(summary.to_string());
                    }
                }
            }
        } else {
            prompt_blocks.push("*(No active scenario blocks)*".to_string());
        }

        prompt_blocks.push("\n[L1: ATOMIC FACTS & PREFERENCES]".to_string());
        if !l1_atomic.is_empty() {
            for (i, it) in l1_atomic.iter().enumerate() {
                let t = it.get("type").and_then(|t| t.as_str()).unwrap_or("fact");
                let c = it.get("content").and_then(|c| c.as_str()).unwrap_or("");
                prompt_blocks.push(format!("{}. [{}] {}", i + 1, t.to_uppercase(), c));
            }
        } else {
            prompt_blocks.push("*(No atomic memories retrieved)*".to_string());
        }

        prompt_blocks.push("==================================================".to_string());
        let formatted_prompt = prompt_blocks.join("\n");

        Ok(serde_json::json!({
            "L1_atomic": l1_atomic,
            "L2_scenarios": l2_scenarios,
            "L3_profile": l3_profile,
            "formatted_prompt": formatted_prompt
        }))
    })?;

    value_to_py_any(py, &res_json)
}

// ═══════════════════════════════════════════════════════════════════════
// Module registration
// ═══════════════════════════════════════════════════════════════════════

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // File I/O
    m.add_function(wrap_pyfunction!(save_json_atomic, m)?)?;
    // JSON normalisation + hashing
    m.add_function(wrap_pyfunction!(normalize_and_hash_args, m)?)?;
    // Secret redaction
    m.add_function(wrap_pyfunction!(scrub_string, m)?)?;
    m.add_function(wrap_pyfunction!(scrub_obj, m)?)?;
    // JSON utilities
    m.add_function(wrap_pyfunction!(json_dumps_sorted, m)?)?;
    m.add_function(wrap_pyfunction!(json_canonical_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(read_file_utf8, m)?)?;
    // ANSI string processing
    m.add_function(wrap_pyfunction!(clip_ansi_string, m)?)?;
    m.add_function(wrap_pyfunction!(visible_width, m)?)?;
    // Doom-loop detection
    m.add_function(wrap_pyfunction!(detect_doom_loop_rust, m)?)?;
    // Layered memories formatting
    m.add_function(wrap_pyfunction!(format_layered_memories_rust, m)?)?;
    Ok(())
}
