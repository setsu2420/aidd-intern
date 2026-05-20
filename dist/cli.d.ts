#!/usr/bin/env node
import { Command } from 'commander';

/**
 * aidd-intern — Node.js CLI for smoke tests, integration checks, and eval runs.
 */

declare function createProgram(): Command;

export { createProgram };
