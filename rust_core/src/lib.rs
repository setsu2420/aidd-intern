use pyo3::prelude::*;
use pyo3::exceptions::PyIOError;
use std::io::Write;
use std::path::Path;
use tempfile::NamedTempFile;

/// Atomically saves the bytes content to the specified path by writing to a temporary file
/// in the same directory and renaming it to the target file.
/// This function releases the Python GIL during the I/O operations.
#[pyfunction]
fn save_json_atomic(py: Python<'_>, path: &str, content: &[u8]) -> PyResult<()> {
    py.allow_threads(|| -> PyResult<()> {
        let target_path = Path::new(path);
        
        // Ensure the directory exists
        if let Some(parent) = target_path.parent() {
            if !parent.exists() {
                std::fs::create_dir_all(parent)
                    .map_err(|e| PyIOError::new_err(format!("Failed to create directories: {}", e)))?;
            }
        }

        // Create a temporary file in the same directory to guarantee an atomic rename
        let parent_dir = target_path.parent().unwrap_or_else(|| Path::new("."));
        let mut temp_file = NamedTempFile::new_in(parent_dir)
            .map_err(|e| PyIOError::new_err(format!("Failed to create temporary file: {}", e)))?;

        // Write the data to the temporary file
        temp_file.write_all(content)
            .map_err(|e| PyIOError::new_err(format!("Failed to write to temporary file: {}", e)))?;

        // Sync to disk to ensure integrity before rename
        temp_file.flush()
            .map_err(|e| PyIOError::new_err(format!("Failed to flush temporary file: {}", e)))?;

        // Atomically rename (persist) the temporary file to the target path
        temp_file.persist(target_path)
            .map_err(|e| PyIOError::new_err(format!("Failed to atomically replace target file: {}", e)))?;

        Ok(())
    })
}

/// A Python module implemented in Rust.
#[pymodule]
fn aidd_intern_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(save_json_atomic, m)?)?;
    Ok(())
}
