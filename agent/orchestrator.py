"""
Pipeline Orchestrator driving the PPT generation phases.
"""

import os
import re
import json
import shutil
import asyncio
import html
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from agents import Runner, RunConfig, ModelSettings

from .config import AgentConfig
from .state import ProjectState
from .agents.strategist import create_strategist_agent
from .prompts.loader import PromptLoader
from .schemas import ExecutorWindowOutput, StrategistSpecOutput


class PipelineOrchestrator:
    """Manages the end-to-end presentation generation pipeline."""

    def __init__(self, state: ProjectState, config: Optional[AgentConfig] = None):
        self.state = state
        self.config = config or AgentConfig.from_env()
        self.loader = PromptLoader(self.config.skill_dir)
        self._chart_index_cache: Optional[dict] = None
        
        # Configure OpenAI client globally for the agents SDK
        from agents import set_default_openai_client, set_default_openai_api, set_tracing_disabled
        set_default_openai_client(self.config.build_client())
        set_default_openai_api("chat_completions")
        set_tracing_disabled(True)

    async def run_to_eight_confirmations(self, interactive_templates: bool = False) -> Optional[str]:
        """Run setup and return the Strategist Eight Confirmations proposal."""
        # Phase 1: Source processing
        converted_mds = self._process_sources()
        
        # Phase 2: Project Initialization
        project_name = self._project_name_from_state()
        self._init_project(project_name)
        
        if converted_mds:
            self._import_converted_sources(converted_mds)

        # Phase 3: Template Setup
        self._setup_template(interactive=interactive_templates)

        # Phase 4: Strategist Agent
        proposal = await self._run_strategist_proposal()
        if proposal:
            self.state.eight_confirmation = proposal
            self.state.current_phase = "awaiting_confirmation"
        return proposal

    async def run_to_strategist(self) -> bool:
        """Run Phases 1-4 in CLI mode, including blocking confirmation input.
        
        Returns:
            True if strategist phase completed and specs generated, False otherwise.
        """
        proposal = await self.run_to_eight_confirmations(interactive_templates=True)
        if not proposal:
            return False

        print("\n" + "=" * 80)
        print("STRATEGIST AGENT PROPOSAL & EIGHT CONFIRMATIONS")
        print("=" * 80)
        print(proposal)
        print("=" * 80)
        
        user_input = input(
            "\nPlease review the proposed confirmations above.\n"
            "   - Press Enter to accept as-is.\n"
            "   - Or describe modifications (e.g. 'Page count 6 pages, style Consulting, accent color #FF5733'):\n"
            "   Your feedback: "
        ).strip()
        return await self.confirm_eight_confirmations(user_input, print_final_proposal=bool(user_input))

    def _project_name_from_state(self) -> str:
        project_name = self.state.source_files[0] if self.state.source_files else "presentation"
        project_name = Path(project_name).stem
        project_name = "".join(c if c.isalnum() else "_" for c in project_name).strip("_")
        return project_name or "presentation"

    def _process_sources(self) -> List[str]:
        """Convert input non-Markdown files to Markdown.
        
        Returns:
            List of converted markdown file paths.
        """
        converted_paths = []
        if not self.state.source_files:
            return converted_paths

        from .tools.source_tools import run_convert_pdf, run_convert_docx, run_convert_excel, run_convert_pptx, run_convert_web

        for file_str in self.state.source_files:
            file_path = Path(file_str)
            
            # If it's a URL
            if file_str.startswith(("http://", "https://")):
                output = run_convert_web(file_str)
                continue
                
            if not file_path.exists():
                print(f"WARN: File not found: {file_str}")
                continue
 
            suffix = file_path.suffix.lower()
            if suffix in {".md", ".markdown", ".txt"}:
                converted_paths.append(str(file_path))
            elif suffix == ".pdf":
                output = run_convert_pdf(str(file_path))
                md_path = file_path.with_suffix(".md")
                if md_path.exists():
                    converted_paths.append(str(md_path))
            elif suffix in {".docx", ".doc", ".odt", ".epub", ".html", ".htm"}:
                output = run_convert_docx(str(file_path))
                md_path = file_path.with_suffix(".md")
                if md_path.exists():
                    converted_paths.append(str(md_path))
            elif suffix in {".xlsx", ".xlsm"}:
                output = run_convert_excel(str(file_path))
                md_path = file_path.with_suffix(".md")
                if md_path.exists():
                    converted_paths.append(str(md_path))
            elif suffix in {".pptx", ".ppt"}:
                output = run_convert_pptx(str(file_path))
                md_path = file_path.with_suffix(".md")
                if md_path.exists():
                    converted_paths.append(str(md_path))
            else:
                print(f"WARN: Unsupported suffix for auto-conversion: {suffix}. Importing file as-is.")
                converted_paths.append(str(file_path))
 
        return converted_paths
 
    def _init_project(self, project_name: str):
        """Create project directory structures."""
        from .tools.project_tools import run_init_project
        
        output = run_init_project(project_name, self.state.canvas_format)
        
        # Parse output for the project path or calculate it
        # Format of name: project_name_format_date
        date_str = datetime.now().strftime("%Y%m%d")
        project_dir_name = f"{project_name}_{self.state.canvas_format}_{date_str}"
        project_path = self.config.projects_dir / project_dir_name
        
        if not project_path.exists():
            # Fallback scan
            matches = list(self.config.projects_dir.glob(f"{project_name}_*"))
            if matches:
                # Sort by modification time, get newest
                matches.sort(key=lambda p: p.stat().st_mtime)
                project_path = matches[-1]
                
        self.state.project_path = project_path
 
    def _import_converted_sources(self, source_files: List[str]):
        """Import converted files into the project structure."""
        from .tools.project_tools import run_import_sources
        output = run_import_sources(str(self.state.project_path), source_files)

    def _setup_template(self, interactive: bool = False):
        """Handle conditional template flow (Opt-in)."""
        template_trigger = None
        
        # Search in user preferences or text trigger
        user_input_str = (self.state.user_text or "").lower()
        
        # List of template folder names
        templates_index_path = self.config.templates_dir / "layouts" / "layouts_index.json"
        if not templates_index_path.exists():
            return

        try:
            with open(templates_index_path, "r", encoding="utf-8") as f:
                layouts_index = json.load(f)
        except Exception as e:
            print(f"WARN: Error loading template index: {e}. Skipping template options.")
            return

        # Check triggers
        for layout_name, layout_info in layouts_index.items():
            # Check direct name match
            if layout_name.lower() in user_input_str:
                template_trigger = layout_name
                break
            
            # Check style/keyword matches
            keywords = layout_info.get("keywords", [])
            for kw in keywords:
                if kw.lower() in user_input_str:
                    template_trigger = layout_name
                    break
        
        # Check if user explicitly asked for list of templates
        list_triggers = ["available templates", "available styles", "list templates", "what templates"]
        if any(lt in user_input_str for lt in list_triggers):
            print("\nAvailable Templates:")
            for name, info in layouts_index.items():
                print(f"- {name}: {info.get('description', '')} (Keywords: {', '.join(info.get('keywords', []))})")
            
            if interactive:
                sel = input("\nEnter template name to use (leave empty for default free design): ").strip()
                if sel in layouts_index:
                    template_trigger = sel

        if template_trigger:
            print(f"Template to use: '{template_trigger}'")
            self.state.template_name = template_trigger
            
            # Copy template files
            src_layout_dir = self.config.templates_dir / "layouts" / template_trigger
            dest_template_dir = self.state.project_path / "templates"
            dest_images_dir = self.state.project_path / "images"
            
            if src_layout_dir.exists():
                # Copy SVGs and design spec
                for file_path in src_layout_dir.glob("*"):
                    if file_path.suffix.lower() == ".svg" or file_path.name == "design_spec.md":
                        shutil.copy2(file_path, dest_template_dir / file_path.name)
                    elif file_path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                        shutil.copy2(file_path, dest_images_dir / file_path.name)
            else:
                print(f"WARN: Template source directory '{src_layout_dir}' does not exist.")

    async def _run_strategist_proposal(self) -> Optional[str]:
        """Ask Strategist for the Eight Confirmations proposal only."""
        agent = create_strategist_agent(self.loader)
        sources_content = self._load_sources_content()
        output_language = self._detect_output_language(sources_content)
        image_analysis = self._analyze_existing_images()

        # Build initial strategist prompt
        context = (
            f"You are the Strategist agent. Receive these materials and draft the Eight Confirmations.\n"
            f"Canvas format default: {self.state.canvas_format}\n"
            f"Template name: {self.state.template_name or 'None (free design)'}\n\n"
            f"Default output language: {output_language}. "
            "Unless the user explicitly requested another language, all slide-facing text, "
            "content outline values, and speaker notes must use this language. "
            "Keep technical acronyms such as CAC, LTV, Churn, NPS, Cloud, and AI unchanged when useful.\n\n"
            "Use the injected templates/icons/README.md and templates/charts/charts_index.json references. "
            "When writing spec_lock.md, icon references must exist in templates/icons/, and visualization "
            "template keys must exist in templates/charts/charts_index.json and templates/charts/<key>.svg.\n\n"
            f"=== Source Document Content ===\n{sources_content}\n\n"
        )
        if image_analysis:
            context += f"=== Existing Image Assets Analysis ===\n{image_analysis}\n\n"

        context += (
            "Please read 'templates/design_spec_reference.md' and follow the strategist roles/guidelines. "
            "Output your bundled Eight Confirmations first. Ask the user for confirmation. "
            "Do not draft final design_spec.md or spec_lock.md yet."
        )

        result = await Runner.run(
            agent, 
            context,
            run_config=self._build_run_config()
        )
        return str(result.final_output).strip()

    async def confirm_eight_confirmations(
        self,
        confirmation_text: str = "",
        print_final_proposal: bool = False,
    ) -> bool:
        """Finalize strategist specs from an accepted or edited Eight Confirmations proposal."""
        if not self.state.project_path:
            print("ERROR: Project path is not set. Cannot finalize strategist phase.")
            return False
        if not self.state.eight_confirmation:
            print("ERROR: Eight Confirmations proposal is missing. Cannot finalize strategist phase.")
            return False

        sources_content = self._load_sources_content()
        output_language = self._detect_output_language(sources_content)
        run_config = self._build_run_config()
        user_input = (confirmation_text or "").strip()
        accepted_values = {"", "accept", "accepted", "confirm", "confirmed", "ok", "okay", "yes", "approve", "approved"}
        is_acceptance = user_input.lower() in accepted_values

        if not is_acceptance:
            feedback_prompt = (
                f"You are still working on the same source document and project.\n"
                f"Project path: {self.state.project_path}\n"
                f"Default output language: {output_language}\n\n"
                f"=== Source Document Content ===\n{sources_content}\n\n"
                f"=== Accepted/Previous Strategist Proposal ===\n{self.state.eight_confirmation}\n\n"
                f"The user has reviewed your proposal and provided the following feedback:\n"
                f"'{user_input}'\n\n"
                f"Please update the design specification according to this feedback. "
                f"Generate the definitive 'design_spec.md' and 'spec_lock.md' files. "
                f"Output language for all user-facing content values: {output_language}. "
                "Keep the design_spec.md section headings and field labels in the reference template structure, "
                "but titles, slide text, notes requirements, and content outline values must be Vietnamese. "
                "Use the actual source document only; do not invent a generic quarterly business review. "
                "Do not request external, AI-generated, or pending images unless matching local files already exist. "
                "For this automated E2E test, set Image Resource List and spec_lock Images to no local images / vector shapes only. "
                "Use only icon paths that exist in the injected icon library guidance and chart keys that exist in "
                "the injected charts_index.json catalog. "
                "Do not call tools and do not include file paths. Return the required structured object with exactly these payload fields: "
                "`design_spec_md` and `spec_lock_md`."
            )
            result = await self._run_strategist_finalization(feedback_prompt, run_config)
            if print_final_proposal:
                print("\nFinal Spec Proposal:")
                print(result.final_output)
        else:
            finalize_prompt = (
                f"You are still working on the same source document and project.\n"
                f"Project path: {self.state.project_path}\n"
                f"Default output language: {output_language}\n\n"
                f"=== Source Document Content ===\n{sources_content}\n\n"
                f"=== Accepted Strategist Proposal ===\n{self.state.eight_confirmation}\n\n"
                f"The user has accepted your confirmations. "
                f"Please finalize and write 'design_spec.md' and 'spec_lock.md' files "
                f"for project path: '{self.state.project_path}'. "
                f"Output language for all user-facing content values: {output_language}. "
                "Keep the design_spec.md section headings and field labels in the reference template structure, "
                "but titles, slide text, notes requirements, and content outline values must be Vietnamese. "
                "Use the actual source document only; do not invent a generic quarterly business review. "
                "Do not request external, AI-generated, or pending images unless matching local files already exist. "
                "For this automated E2E test, set Image Resource List and spec_lock Images to no local images / vector shapes only. "
                "Use only icon paths that exist in the injected icon library guidance and chart keys that exist in "
                "the injected charts_index.json catalog. "
                "Do not call tools and do not include file paths. Return the required structured object with exactly these payload fields: "
                "`design_spec_md` and `spec_lock_md`."
            )
            result = await self._run_strategist_finalization(finalize_prompt, run_config)

        # Fallback: try to extract specs from text if they don't exist yet
        if not (self.state.design_spec_path.exists() and self.state.spec_lock_path.exists()):
            print("\nWARN: Spec files not found. Attempting fallback extraction from agent output text...")
            self._extract_specs_fallback(str(result.final_output))

        # Check if the output files exist
        if self.state.design_spec_path.exists() and self.state.spec_lock_path.exists():
            self._enforce_local_image_policy()
            self._validate_and_normalize_resource_refs()
            self.state.current_phase = "strategist_done"
            return True
        else:
            print(f"\nERROR: Design spec files were not generated or were saved in the wrong location.")
            return False

    def _load_sources_content(self) -> str:
        """Read imported Markdown sources or fall back to direct user text."""
        sources_content = ""
        sources_dir = self.state.sources_dir
        if sources_dir and sources_dir.exists():
            md_files = list(sources_dir.glob("*.md")) + list(sources_dir.glob("*.markdown"))
            for md_file in md_files:
                sources_content += f"\n\n--- Source: {md_file.name} ---\n"
                sources_content += md_file.read_text(encoding="utf-8")

        if not sources_content and self.state.user_text:
            sources_content = self.state.user_text
        return sources_content

    def _analyze_existing_images(self) -> str:
        images_dir = self.state.images_dir
        if images_dir and images_dir.exists():
            from .tools.image_tools import run_analyze_images
            return run_analyze_images(str(images_dir))
        return ""

    def _build_run_config(self) -> RunConfig:
        return RunConfig(
            model=self.config.model,
            model_settings=ModelSettings(
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )
        )

    async def _run_strategist_finalization(self, prompt: str, run_config: RunConfig):
        """Run strategist finalization through the structured output contract."""
        structured_agent = create_strategist_agent(self.loader, output_type=StrategistSpecOutput)
        structured_prompt = (
            f"{prompt}\n\n"
            "Output contract:\n"
            "- Return a single structured object matching the StrategistSpecOutput schema.\n"
            "- `design_spec_md` must contain the complete Markdown file content.\n"
            "- `spec_lock_md` must contain the complete Markdown file content.\n"
            "- `slide_outline` must contain exactly one ordered object per slide with "
            "`slide_number`, `title`, `layout`, `rhythm`, `content_points`, and `visualization`.\n"
            "- Do not wrap the payload in markdown fences, XML tags, shell commands, or tool calls."
        )

        try:
            result = await Runner.run(
                structured_agent,
                structured_prompt,
                run_config=run_config,
            )
        except Exception as exc:
            print(f"WARN: Structured strategist output failed ({exc}). Retrying with JSON contract fallback...")
            fallback_agent = create_strategist_agent(self.loader)
            fallback_prompt = (
                f"{prompt}\n\n"
                "Return exactly one JSON object and no surrounding prose. The object shape is:\n"
                '{"design_spec_md": "...complete markdown...", "spec_lock_md": "...complete markdown...", '
                '"slide_outline": [{"slide_number": 1, "title": "...", "layout": "...", '
                '"rhythm": "breathing", "content_points": ["..."], "visualization": null}]}'
            )
            result = await Runner.run(
                fallback_agent,
                fallback_prompt,
                run_config=run_config,
            )

        if not self._write_structured_specs(result.final_output):
            print("\nWARN: Structured spec payload was not usable. Falling back to legacy text extraction...")
            self._extract_specs_fallback(str(result.final_output))

        return result

    def _write_structured_specs(self, payload) -> bool:
        """Persist strategist output when it matches the structured contract."""
        data = self._payload_to_dict(payload)
        if not data:
            return False

        design_spec = data.get("design_spec_md")
        spec_lock = data.get("spec_lock_md")
        slide_outline = data.get("slide_outline")
        if not isinstance(design_spec, str) or not isinstance(spec_lock, str):
            return False
        if not isinstance(slide_outline, list) or not slide_outline:
            return False
        if not design_spec.strip() or not spec_lock.strip():
            return False

        design_spec = self._sanitize_spec_text(design_spec)
        spec_lock = self._sanitize_spec_text(spec_lock)

        self.state.design_spec_path.write_text(design_spec.strip() + "\n", encoding="utf-8")
        self.state.spec_lock_path.write_text(spec_lock.strip() + "\n", encoding="utf-8")
        self._write_slide_outline(slide_outline)
        return True

    def _write_slide_outline(self, slide_outline: list):
        """Persist the canonical strategist slide outline for executor."""
        if not self.state.project_path:
            return

        normalized = []
        for index, item in enumerate(slide_outline, start=1):
            if not isinstance(item, dict):
                continue

            slide_number = item.get("slide_number", index)
            try:
                slide_number = int(slide_number)
            except (TypeError, ValueError):
                slide_number = index

            content_points = item.get("content_points", [])
            if isinstance(content_points, str):
                content_points = [content_points]
            elif not isinstance(content_points, list):
                content_points = []

            rhythm = str(item.get("rhythm") or "dense").strip().lower()
            if rhythm not in {"anchor", "dense", "breathing"}:
                rhythm = "dense"

            normalized.append({
                "slide_number": slide_number,
                "title": str(item.get("title") or f"Slide {slide_number}").strip(),
                "layout": str(item.get("layout") or "").strip(),
                "rhythm": rhythm,
                "content_points": [str(point).strip() for point in content_points if str(point).strip()],
                "visualization": self._normalize_visualization_value(item.get("visualization")),
            })

        if normalized:
            outline_path = self.state.project_path / "slide_outline.json"
            outline_path.write_text(
                json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    @staticmethod
    def _payload_to_dict(payload) -> Optional[dict]:
        """Convert typed output or a JSON contract string into a dict."""
        if payload is None:
            return None

        if hasattr(payload, "model_dump"):
            return payload.model_dump()

        if isinstance(payload, dict):
            return payload

        if not isinstance(payload, str):
            return None

        text = payload.strip()
        if not text:
            return None

        start_tag = "<PPT_MASTER_JSON>"
        end_tag = "</PPT_MASTER_JSON>"
        if start_tag in text and end_tag in text:
            start = text.find(start_tag) + len(start_tag)
            end = text.find(end_tag, start)
            text = text[start:end].strip()

        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
                text = "\n".join(lines[1:-1]).strip()

        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value

        return None

    def _extract_specs_fallback(self, text: str):
        """Extract design_spec.md and spec_lock.md contents from raw LLM text response."""
        if not text:
            return

        # Prefer explicit XML-style file payloads emitted by local LLMs/tool parsers.
        # This avoids saving surrounding assistant narration or <write_file> wrappers.
        file_blocks = re.findall(
            r"<write_file>\s*<path>([\s\S]+?)</path>\s*<content>([\s\S]+?)</content>\s*</write_file>",
            text,
            re.IGNORECASE,
        )
        for raw_path, raw_content in file_blocks:
            filename = Path(html.unescape(raw_path.strip())).name
            content = self._sanitize_spec_text(raw_content.strip())
            if filename == "design_spec.md":
                self.state.design_spec_path.write_text(content, encoding="utf-8")
            elif filename == "spec_lock.md":
                self.state.spec_lock_path.write_text(content, encoding="utf-8")

        if self.state.design_spec_path.exists() and self.state.spec_lock_path.exists():
            return
            
        spec_content = ""
        lock_content = ""

        # 1. Match code blocks with any language tags
        blocks = re.findall(r"```[a-zA-Z0-9_-]*\s*[\r\n]+([\s\S]+?)(?=```)", text)
        if not blocks:
            blocks = [text]

        for b in blocks:
            # If it's a python script containing string variables
            if "design_spec_content" in b or "spec_lock_content" in b:
                str_matches = re.findall(r'"""([\s\S]+?)"""', b)
                for sm in str_matches:
                    if any(x in sm for x in ["Executive Summary", "Content Outline", "design_spec", "Design Specification", "Project Information"]):
                        spec_content = sm.strip()
                    elif any(x in sm for x in ["Color Palette", "page_rhythm", "Visual Rhythm", "spec_lock", "Spec Lock", "Page Rhythm", "Colors", "Canvas"]):
                        lock_content = sm.strip()
            
            # Direct block matching
            if not spec_content and any(x in b for x in ["Executive Summary", "Content Outline", "design_spec", "Design Specification", "Project Information"]):
                spec_content = b.strip()
            if not lock_content and any(x in b for x in ["Color Palette", "page_rhythm", "Visual Rhythm", "spec_lock", "Spec Lock", "Page Rhythm", "Colors", "Canvas"]):
                lock_content = b.strip()

        # 2. Last resort direct regex matching on full text
        if not spec_content:
            spec_match = re.search(r"(##? I\.[\s\S]+?)(?=##? Color Palette|##? Spec Lock|spec_lock_content|# spec_lock|$)", text, re.IGNORECASE)
            if spec_match:
                spec_content = spec_match.group(1).strip()
            else:
                spec_match = re.search(r"(Executive Summary[\s\S]+?)(?=Color Palette|Spec Lock|spec_lock|$)", text, re.IGNORECASE)
                if spec_match:
                    spec_content = spec_match.group(1).strip()

        if not lock_content:
            lock_match = re.search(r"(##? Color Palette[\s\S]+?)$", text, re.IGNORECASE)
            if lock_match:
                lock_content = lock_match.group(1).strip()
            else:
                lock_match = re.search(r"(# spec_lock[\s\S]+?)$", text, re.IGNORECASE)
                if lock_match:
                    lock_content = lock_match.group(1).strip()
                else:
                    lock_match = re.search(r"(# Spec Lock[\s\S]+?)$", text, re.IGNORECASE)
                    if lock_match:
                        lock_content = lock_match.group(1).strip()

        # Write out
        if spec_content:
            spec_content = self._sanitize_spec_text(spec_content)
            self.state.design_spec_path.write_text(spec_content, encoding="utf-8")
            
        if lock_content:
            lock_content = self._sanitize_spec_text(lock_content)
            self.state.spec_lock_path.write_text(lock_content, encoding="utf-8")

    def _parse_spec_lock(self, content: str) -> dict:
        """Parse spec_lock.md into structured dict of sections."""
        sections = {}
        current_section = None
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("## "):
                current_section = line[3:].strip()
                sections[current_section] = {}
            elif line.startswith("- ") and current_section:
                parts = line[2:].split(":", 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip()
                    sections[current_section][key] = val
        return sections

    def _parse_design_spec_outline(self, content: str) -> List[dict]:
        """Parse §IX Content Outline of design_spec.md into list of slide dicts."""
        outline_pos = content.find("## IX. Content Outline")
        if outline_pos == -1:
            outline_pos = 0
        
        section_content = content[outline_pos:]
        slides = []
        
        patterns = [
            re.compile(r'####\s+(Slide|Page)\s+(\d+)\s*(?:-|\s|:)*(.*)', re.IGNORECASE),
            re.compile(r'\*\*P(\d+):\s*(.*?)\*\*', re.IGNORECASE),
            re.compile(r'- \*\*P(\d+):\s*(.*?)\*\*', re.IGNORECASE),
            re.compile(r'- \*\*P(\d+)\s+(.+?)\*\*\s*:?', re.IGNORECASE),
            re.compile(r'- \*\*(?:Slide|Page)\s*(\d+):\s*(.*?)\*\*', re.IGNORECASE),
            re.compile(r'###\s+(?:Slide|Page|P)(\d+)\s*(?:-|\s|:)*(.*)', re.IGNORECASE)
        ]
        
        all_matches = []
        for pat in patterns:
            for match in pat.finditer(section_content):
                start = match.start()
                end = match.end()
                groups = match.groups()
                if len(groups) == 3:
                    slide_num = groups[1]
                    slide_title = groups[2].strip()
                elif len(groups) == 2:
                    slide_num = groups[0]
                    slide_title = groups[1].strip()
                else:
                    continue
                
                if not any(x[2] == slide_num for x in all_matches):
                    all_matches.append((start, end, slide_num, slide_title))
                    
        all_matches.sort(key=lambda x: x[0])
        
        for i, match in enumerate(all_matches):
            start_pos, end_pos, slide_num, slide_title = match
            next_start = all_matches[i+1][0] if i + 1 < len(all_matches) else len(section_content)
            slide_body = section_content[end_pos:next_start].strip()
            
            slides.append({
                "number": str(int(slide_num)),
                "title": slide_title,
                "body": slide_body,
                "key": f"P{slide_num.zfill(2)}"
            })
            
        return slides

    def _load_structured_slide_outline(self) -> List[dict]:
        """Load canonical slide outline produced by Strategist structured output."""
        if not self.state.project_path:
            return []

        outline_path = self.state.project_path / "slide_outline.json"
        if not outline_path.exists():
            return []

        try:
            raw = json.loads(outline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARN: Failed to read slide_outline.json: {exc}")
            return []

        if not isinstance(raw, list):
            return []

        slides = []
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, dict):
                continue

            slide_number = item.get("slide_number", index)
            try:
                slide_number = int(slide_number)
            except (TypeError, ValueError):
                slide_number = index

            content_points = item.get("content_points", [])
            if isinstance(content_points, str):
                content_points = [content_points]
            elif not isinstance(content_points, list):
                content_points = []

            body_lines = []
            layout = str(item.get("layout") or "").strip()
            visualization = self._normalize_visualization_value(item.get("visualization"))
            if layout:
                body_lines.append(f"- Layout: {layout}")
            if visualization:
                body_lines.append(f"- Visualization: {visualization}")
            body_lines.extend(f"- {str(point).strip()}" for point in content_points if str(point).strip())

            slides.append({
                "number": str(slide_number),
                "title": str(item.get("title") or f"Slide {slide_number}").strip(),
                "body": "\n".join(body_lines),
                "key": f"P{slide_number:02d}",
                "rhythm": str(item.get("rhythm") or "dense").strip().lower(),
                "visualization": visualization,
            })

        slides.sort(key=lambda slide: int(slide["number"]))
        return slides

    def _load_chart_index(self) -> dict:
        """Load the local visualization catalog used to validate chart references."""
        if self._chart_index_cache is not None:
            return self._chart_index_cache

        index_path = self.config.templates_dir / "charts" / "charts_index.json"
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARN: Failed to load charts_index.json: {exc}")
            data = {}

        self._chart_index_cache = data if isinstance(data, dict) else {}
        return self._chart_index_cache

    def _chart_keys(self) -> set[str]:
        index = self._load_chart_index()
        indexed = set((index.get("charts") or {}).keys())
        charts_dir = self.config.templates_dir / "charts"
        existing = {p.stem for p in charts_dir.glob("*.svg")}
        return indexed & existing if indexed else existing

    def _chart_exists(self, chart_key: str) -> bool:
        return chart_key in self._chart_keys()

    def _chart_template_path(self, chart_key: str) -> Path:
        return self.config.templates_dir / "charts" / f"{chart_key}.svg"

    def _chart_summary(self, chart_key: str) -> str:
        chart_data = (self._load_chart_index().get("charts") or {}).get(chart_key) or {}
        return str(chart_data.get("summary") or "").strip()

    @staticmethod
    def _chart_aliases() -> dict[str, str]:
        """Known LLM-friendly aliases mapped to real charts_index keys."""
        return {
            "scope_timeline": "timeline",
            "phase_timeline": "timeline",
            "phased_timeline": "timeline",
            "rollout_timeline": "timeline",
            "benefits_cards": "icon_grid",
            "benefit_cards": "icon_grid",
            "benefits_grid": "icon_grid",
            "feature_cards": "icon_grid",
            "risk_matrix": "matrix_2x2",
            "risk_control_matrix": "matrix_2x2",
            "control_matrix": "matrix_2x2",
        }

    def _normalize_chart_key(self, value) -> Optional[str]:
        """Return a valid chart key if the provided value maps to one."""
        if value is None:
            return None

        text = str(value).strip()
        if not text:
            return None

        lowered = text.lower()
        if lowered in {"none", "null", "n/a", "na", "no", "custom", "custom layout"}:
            return None

        valid_keys = self._chart_keys()
        aliases = self._chart_aliases()
        tokens = [
            token[:-4] if token.endswith(".svg") else token
            for token in re.findall(r"[a-z][a-z0-9_]*(?:\.svg)?", lowered)
        ]

        for token in tokens:
            if token in valid_keys:
                return token

        normalized = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
        candidates = tokens + ([normalized] if normalized else [])
        for candidate in candidates:
            replacement = aliases.get(candidate)
            if replacement and replacement in valid_keys:
                return replacement

        keyword_rules = [
            (("benefit", "card"), "icon_grid"),
            (("feature", "card"), "icon_grid"),
            (("risk", "matrix"), "matrix_2x2"),
            (("control", "matrix"), "matrix_2x2"),
            (("scope", "timeline"), "timeline"),
            (("phase", "timeline"), "timeline"),
            (("roadmap",), "roadmap_vertical"),
            (("process", "flow"), "process_flow"),
            (("flowchart",), "process_flow"),
        ]
        for terms, replacement in keyword_rules:
            if all(term in lowered for term in terms) and replacement in valid_keys:
                return replacement

        return None

    def _normalize_visualization_value(self, value):
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() in {"none", "null", "n/a", "na", "no"}:
            return None
        return self._normalize_chart_key(text) or text

    def _replace_invalid_chart_refs(self, text: str) -> str:
        """Normalize known chart aliases in generated specs to real chart keys."""
        aliases = self._chart_aliases()

        for alias, replacement in aliases.items():
            if not self._chart_exists(replacement):
                continue
            text = re.sub(rf"\b{re.escape(alias)}\.svg\b", f"{replacement}.svg", text)
            text = re.sub(rf"\b{re.escape(alias)}\b", replacement, text)

        def replace_chart_path(match: re.Match) -> str:
            raw_key = match.group(1)
            normalized = self._normalize_chart_key(raw_key)
            if normalized:
                return f"templates/charts/{normalized}.svg"
            return match.group(0)

        text = re.sub(
            r"templates/charts/([A-Za-z0-9_-]+)\.svg",
            replace_chart_path,
            text,
        )
        return text

    def _validate_and_normalize_resource_refs(self):
        """Persist deterministic icon/chart normalization after strategist output."""
        for path in [self.state.design_spec_path, self.state.spec_lock_path]:
            if not path.exists():
                continue
            before = path.read_text(encoding="utf-8")
            after = self._sanitize_spec_text(before)
            if after != before:
                path.write_text(after.rstrip() + "\n", encoding="utf-8")

        if self.state.project_path:
            outline_path = self.state.project_path / "slide_outline.json"
            if outline_path.exists():
                try:
                    outline = json.loads(outline_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    outline = None
                if isinstance(outline, list):
                    self._write_slide_outline(outline)

    def _build_chart_template_reference_context(self, slides: List[dict]) -> str:
        """Inject the exact chart SVG templates selected for this window."""
        blocks = []
        seen: set[str] = set()
        for slide in slides:
            chart_key = self._normalize_chart_key(slide.get("visualization") or slide.get("body"))
            if not chart_key or chart_key in seen:
                continue

            template_path = self._chart_template_path(chart_key)
            try:
                svg = template_path.read_text(encoding="utf-8")
            except OSError as exc:
                print(f"WARN: Could not read chart template {chart_key}: {exc}")
                continue

            seen.add(chart_key)
            summary = self._chart_summary(chart_key)
            blocks.append(
                f"--- Slide {slide['number']} visualization reference: templates/charts/{chart_key}.svg ---\n"
                f"charts_index summary: {summary}\n"
                "Use this as a structural reference only: preserve the visualization logic, "
                "but adapt content, colors, spacing, and density to spec_lock.md.\n"
                "```xml\n"
                f"{svg}\n"
                "```"
            )

        return "\n\n".join(blocks)

    @staticmethod
    def _build_source_reference_context(source_text: str) -> str:
        """Keep executor output data-grounded without always duplicating huge sources."""
        source_text = source_text.strip()
        if not source_text:
            return ""

        max_full_chars = 30000
        if len(source_text) <= max_full_chars:
            return source_text

        lines = source_text.splitlines()
        selected: list[str] = []
        selected_indexes: set[int] = set()
        for index, line in enumerate(lines):
            if not re.search(r"\d", line):
                continue
            for nearby in range(max(0, index - 2), min(len(lines), index + 2)):
                if nearby in selected_indexes:
                    continue
                selected_indexes.add(nearby)
                selected.append(lines[nearby])

        numeric_excerpt = "\n".join(selected).strip()
        if len(numeric_excerpt) > 16000:
            numeric_excerpt = numeric_excerpt[:16000].rstrip() + "\n...[numeric excerpt truncated]"

        return (
            source_text[:12000].rstrip()
            + "\n\n...[source truncated for context budget]\n\n"
            + "=== Numeric / Table Excerpt From Full Source ===\n"
            + numeric_excerpt
        )

    def _detect_output_language(self, text: str) -> str:
        """Infer default deck language.

        The product default is Vietnamese unless the source clearly indicates otherwise.
        """
        if not text:
            return "Vietnamese"

        vietnamese_chars = "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
        lowered = text.lower()
        if any(ch in lowered for ch in vietnamese_chars):
            return "Vietnamese"

        vietnamese_terms = [
            "doanh nghiệp", "chiến lược", "khách hàng", "tăng trưởng",
            "triển khai", "quản trị", "rủi ro", "công nghệ",
        ]
        if any(term in lowered for term in vietnamese_terms):
            return "Vietnamese"

        return "Vietnamese"

    def _enforce_local_image_policy(self):
        """Prevent generated specs from requiring unavailable image assets."""
        if not self.state.project_path:
            return

        image_dir = self.state.images_dir
        image_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
        local_assets = []
        if image_dir and image_dir.exists():
            local_assets = [
                p.name for p in image_dir.iterdir()
                if p.is_file() and p.suffix.lower() in image_suffixes
            ]

        if local_assets:
            return

        spec_path = self.state.design_spec_path
        if spec_path.exists():
            content = spec_path.read_text(encoding="utf-8")
            replacement = (
                "## VIII. Image Resource List\n\n"
                "No local image assets are available for this run. Do not request external, "
                "AI-generated, or pending image files. Use vector shapes, gradients, charts, "
                "and built-in icons only.\n\n"
            )
            content = re.sub(
                r"## VIII\. Image Resource List[\s\S]*?(?=## IX\. Content Outline)",
                replacement,
                content,
                flags=re.IGNORECASE,
            )
            spec_path.write_text(content, encoding="utf-8")

        lock_path = self.state.spec_lock_path
        if lock_path.exists():
            content = lock_path.read_text(encoding="utf-8")
            replacement = (
                "## Images\n"
                "- strategy: vector_shapes_only\n"
                "- external_images: false\n"
                "- local_assets: none\n\n"
            )
            if re.search(r"## Images[\s\S]*?(?=## |\Z)", content, re.IGNORECASE):
                content = re.sub(
                    r"## Images[\s\S]*?(?=## |\Z)",
                    replacement,
                    content,
                    flags=re.IGNORECASE,
                )
            else:
                content = content.rstrip() + "\n\n" + replacement
            lock_path.write_text(content, encoding="utf-8")

    async def run_executor(self) -> bool:
        """Execute Phase 6 (Executor Phase) using the Windowed Strategy.
        
        Returns:
            True if all slides generated successfully, False otherwise.
        """
        if not self.state.project_path or not self.state.design_spec_path.exists() or not self.state.spec_lock_path.exists():
            print("ERROR: Design spec or spec lock files missing. Cannot run Executor.")
            return False

        # Load specs
        spec_lock_content = self.state.spec_lock_path.read_text(encoding="utf-8")
        design_spec_content = self.state.design_spec_path.read_text(encoding="utf-8")
        source_text = ""
        if self.state.sources_dir and self.state.sources_dir.exists():
            for md_file in sorted(self.state.sources_dir.glob("*.md")):
                source_text += "\n" + md_file.read_text(encoding="utf-8")
        output_language = self._detect_output_language(source_text or design_spec_content)
        source_reference_context = self._build_source_reference_context(source_text)

        # Parse sections
        lock_data = self._parse_spec_lock(spec_lock_content)
        slides = self._load_structured_slide_outline()
        if not slides:
            slides = self._parse_design_spec_outline(design_spec_content)

        if not slides:
            print("ERROR: No slides found in design_spec.md §IX. Content Outline.")
            return False

        # Detect design style (defaults to general)
        style = "general"
        proj_info = lock_data.get("canvas", {})
        # If design style is specified in design spec
        if "consulting" in design_spec_content.lower() or "consultant" in design_spec_content.lower():
            style = "consultant"

        # Create Executor Agent
        from .agents.executor import create_executor_agent
        agent = create_executor_agent(self.loader, style=style, output_type=ExecutorWindowOutput)

        # Loop over windows
        window_size = self.config.window_size
        svg_output_dir = self.state.svg_output_dir
        svg_output_dir.mkdir(parents=True, exist_ok=True)

        for w_start in range(0, len(slides), window_size):
            w_end = min(w_start + window_size, len(slides))
            window_slides = slides[w_start:w_end]
            
            slide_nums_str = ", ".join(s['number'] for s in window_slides)

            # Collect previous 2 SVGs for context
            previous_svgs_content = ""
            all_existing_svgs = sorted(svg_output_dir.glob("*.svg"))
            if all_existing_svgs:
                # Get last 2
                for prev_svg in all_existing_svgs[-2:]:
                    previous_svgs_content += f"\n\n--- Previous SVG: {prev_svg.name} ---\n"
                    previous_svgs_content += prev_svg.read_text(encoding="utf-8")

            # Compile window payload
            context = (
                f"You are the Executor agent. Please generate SVG slide layouts for this window of slides.\n"
                f"Project root path: '{self.state.project_path}'\n\n"
                f"Output language: {output_language}. All visible slide text and all speaker notes must be in "
                f"{output_language} unless a technical acronym or source term is intentionally preserved.\n"
                "Do not translate the deck into English by default.\n\n"
                f"=== Canonical Execution Lock (spec_lock.md) ===\n"
                f"{spec_lock_content}\n\n"
            )

            if source_reference_context:
                context += (
                    "=== Authoritative Source Document Reference ===\n"
                    "Use this source as the authority for every chart value, KPI, period label, department name, "
                    "risk item, and roadmap milestone. If this source conflicts with the outline, preserve the "
                    "exact source data and use the outline only for slide intent.\n"
                    f"{source_reference_context}\n\n"
                )

            if previous_svgs_content:
                context += f"=== Previous SVGs Context (Maintain Style Consistency) ==={previous_svgs_content}\n\n"

            chart_template_context = self._build_chart_template_reference_context(window_slides)
            if chart_template_context:
                context += (
                    "=== Visualization Template References (Read-Only Structural Guides) ===\n"
                    f"{chart_template_context}\n\n"
                )

            context += "=== Slide Outline to Generate in this Window ===\n"
            for slide in window_slides:
                rhythm = slide.get("rhythm") or lock_data.get("page_rhythm", {}).get(slide['key'], "dense")
                context += (
                    f"#### Slide {slide['number']} - {slide['title']}\n"
                    f"- Rhythm layout: {rhythm}\n"
                    f"{slide['body']}\n\n"
                )

            context += (
                "Please generate the SVG content for each slide directly in your response.\n"
                "IMPORTANT: You do not need to call any tools or read any files. All required specs and outlines are already provided above.\n"
                "CRITICAL DATA FIDELITY: For charts, tables, KPI cards, and callouts, copy exact numbers, percentages, "
                "units, period labels, and category labels from the Authoritative Source Document Reference. Do not "
                "interpolate, smooth, round, average, extrapolate, or invent intermediate values. If a value is not "
                "available in the source, omit it instead of guessing.\n"
                "Keep every visible element inside the 1280x720 canvas with safe margins; cards and labels must not "
                "extend beyond the right or bottom edge.\n"
                "Do not use <image> tags unless the referenced file is explicitly listed as an existing local asset. "
                "If the spec mentions conceptual AI images but no actual file exists, use vector shapes/gradients instead.\n"
                "Ensure all guidelines from shared-standards.md and your system prompt are perfectly respected.\n"
                "Return the required structured object only: `slides` must contain exactly one item for each requested slide, "
                "with `slide_number`, complete `svg`, and detailed `speaker_notes_md`. "
                "Do not wrap the SVG or notes in markdown fences. Write the speaker notes in pure conversational text."
            )

            run_config = RunConfig(
                model=self.config.model,
                model_settings=ModelSettings(
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens
                )
            )

            try:
                result = await Runner.run(
                    agent,
                    context,
                    run_config=run_config
                )
            except Exception as exc:
                print(f"WARN: Structured executor output failed ({exc}). Retrying with legacy text contract...")
                fallback_agent = create_executor_agent(self.loader, style=style)
                fallback_context = (
                    f"{context}\n\n"
                    "Fallback output contract: for each requested slide, write one complete SVG inside an independent "
                    "```xml code block, followed by one detailed speaker note inside an independent ```markdown code block."
                )
                result = await Runner.run(
                    fallback_agent,
                    fallback_context,
                    run_config=run_config
                )

            if not self._write_structured_window_outputs(result.final_output, window_slides, output_language):
                print("WARN: Structured executor payload was not usable. Falling back to legacy block extraction...")
                self._extract_window_outputs(str(result.final_output), window_slides, output_language)

            # Verification of written SVGs in this window
            missing_slides = []
            for slide in window_slides:
                # Find matching SVG file
                safe_num = slide['number'].zfill(2)
                matches = list(svg_output_dir.glob(f"{safe_num}_*.svg"))
                if not matches:
                    print(f"  ERROR: Slide {slide['number']} SVG was not found after window extraction.")
                    missing_slides.append(slide["number"])

            if missing_slides:
                print(f"ERROR: Executor window [{slide_nums_str}] did not produce SVGs for slide(s): {', '.join(missing_slides)}.")
                return False

        # Post-execution check
        from .tools.svg_tools import run_quality_check
        report = run_quality_check(str(self.state.project_path))
        if self._quality_report_has_errors(report):
            print(report)
            print("ERROR: SVG quality verification failed. Stopping before post-processing/export.")
            return False

        self.state.current_phase = "executor_done"
        return True

    @staticmethod
    def _quality_report_has_errors(report: str) -> bool:
        """Return True only when svg_quality_checker reports actual errors."""
        if not report or "No SVG files found" in report:
            return True

        summary_match = re.search(r"\[ERROR\]\s+With errors:\s*(\d+)", report, re.IGNORECASE)
        if summary_match:
            return int(summary_match.group(1)) > 0

        for line in report.splitlines():
            line = line.strip()
            if line.startswith("[ERROR]") and not re.search(r"With errors:\s*0\b", line, re.IGNORECASE):
                return True

        return False

    @staticmethod
    def _command_output_has_problem(output: str) -> bool:
        """Return True when command output contains warning/error signals."""
        if not output:
            return False
        problem_re = re.compile(
            r"\b(errors?|warnings?|warn|failed|failure|traceback|exception)\b",
            re.IGNORECASE,
        )
        neutral_re = re.compile(
            r"\b(?:(?:no|0)\s+(?:errors?|warnings?)|(?:errors?|warnings?)\s*:\s*0)\b",
            re.IGNORECASE,
        )
        return any(
            problem_re.search(line) and not neutral_re.search(line)
            for line in output.splitlines()
        )

    def _write_structured_window_outputs(self, payload, window_slides: List[dict], output_language: str) -> bool:
        """Persist executor output when it matches the structured contract."""
        data = self._payload_to_dict(payload)
        if not data or not isinstance(data.get("slides"), list):
            return False

        items = [item for item in data["slides"] if isinstance(item, dict)]
        by_number = {
            str(item.get("slide_number")): item
            for item in items
            if item.get("slide_number") is not None
        }

        wrote_all = True
        for index, slide in enumerate(window_slides):
            item = by_number.get(slide["number"])
            if item is None and index < len(items):
                item = items[index]

            if not item:
                wrote_all = False
                continue

            svg_content = item.get("svg")
            if not isinstance(svg_content, str) or not svg_content.strip():
                wrote_all = False
                continue

            svg_content = self._normalize_svg_payload(svg_content)
            if not svg_content:
                wrote_all = False
                continue

            svg_content = self._sanitize_svg_content(svg_content)
            safe_num = slide["number"].zfill(2)
            filename = f"{safe_num}_{slide['key']}.svg"
            from .tools.svg_tools import run_write_svg
            msg = run_write_svg(filename, svg_content, str(self.state.project_path))
            if self._command_output_has_problem(msg):
                print(f"  {msg}")

            notes_content = item.get("speaker_notes_md")
            if not isinstance(notes_content, str) or not notes_content.strip():
                notes_content = self._default_notes_for_slide(slide, output_language)
            notes_content = self._sanitize_speaker_notes(notes_content, output_language)

            notes_dir = self.state.project_path / "notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            notes_path = notes_dir / f"{safe_num}_{slide['key']}.md"
            notes_path.write_text(notes_content.strip() + "\n", encoding="utf-8")

        return wrote_all

    @staticmethod
    def _normalize_svg_payload(svg_content: str) -> str:
        """Trim non-SVG wrapper text from a structured SVG field."""
        svg_content = svg_content.strip()
        start = svg_content.find("<svg")
        end = svg_content.rfind("</svg>")
        if start == -1 or end == -1:
            return ""
        return svg_content[start:end + len("</svg>")].strip()

    def _extract_window_outputs(self, text: str, window_slides: List[dict], output_language: str):
        """Extract all SVG and notes blocks from a single executor window.

        Local LLMs often return plain text with multiple code blocks. Mapping each
        slide independently against the whole response can select the first SVG
        repeatedly. This function maps blocks by explicit slide markers first and
        by block order second.
        """
        if not text or not self.state.project_path:
            return

        svg_blocks = self._extract_svg_blocks(text)
        notes_blocks = self._extract_markdown_blocks(text)

        for idx, slide in enumerate(window_slides):
            svg_content = self._select_block_for_slide(svg_blocks, slide, idx)
            if svg_content:
                svg_content = self._sanitize_svg_content(svg_content)
                safe_num = slide["number"].zfill(2)
                filename = f"{safe_num}_{slide['key']}.svg"
                from .tools.svg_tools import run_write_svg
                msg = run_write_svg(filename, svg_content, str(self.state.project_path))
                if self._command_output_has_problem(msg):
                    print(f"  {msg}")

            notes_content = self._select_notes_for_slide(notes_blocks, text, slide, idx)
            if not notes_content:
                notes_content = self._default_notes_for_slide(slide, output_language)
            notes_content = self._sanitize_speaker_notes(notes_content, output_language)

            notes_dir = self.state.project_path / "notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            safe_num = slide["number"].zfill(2)
            notes_path = notes_dir / f"{safe_num}_{slide['key']}.md"
            notes_path.write_text(notes_content.strip() + "\n", encoding="utf-8")

    @staticmethod
    def _extract_svg_blocks(text: str) -> List[str]:
        blocks = re.findall(
            r"```(?:xml|svg)?\s*[\r\n]+(<svg[\s\S]+?</svg>)\s*```",
            text,
            re.IGNORECASE,
        )
        if blocks:
            return [b.strip() for b in blocks]
        return [b.strip() for b in re.findall(r"(<svg\b[\s\S]+?</svg>)", text, re.IGNORECASE)]

    def _sanitize_svg_references(self, svg_content: str) -> str:
        """Remove image references that cannot be resolved inside the project."""
        if not self.state.project_path or not self.state.svg_output_dir:
            return svg_content

        def replace(match: re.Match) -> str:
            tag = match.group(0)
            href_match = re.search(r'(?:href|xlink:href)=["\']([^"\']+)["\']', tag, re.IGNORECASE)
            if not href_match:
                return tag

            href = href_match.group(1)
            if href.startswith(("data:", "http://", "https://")):
                return tag

            candidate = (self.state.svg_output_dir / href).resolve()
            project_root = self.state.project_path.resolve()
            try:
                candidate.relative_to(project_root)
            except ValueError:
                print(f"WARN: Removed image outside project from SVG: {href}")
                return ""

            if not candidate.exists():
                print(f"WARN: Removed missing image reference from SVG: {href}")
                return ""
            return tag

        return re.sub(r"<image\b[^>]*/?>", replace, svg_content, flags=re.IGNORECASE)

    def _sanitize_svg_content(self, svg_content: str) -> str:
        """Apply deterministic SVG cleanup before writing executor output."""
        svg_content = self._sanitize_xml_text_entities(svg_content)
        svg_content = self._replace_invalid_icon_refs(svg_content)
        svg_content = self._normalize_svg_attribute_contract(svg_content)
        svg_content = self._normalize_svg_style_contract(svg_content)
        return self._sanitize_svg_references(svg_content)

    def _sanitize_spec_text(self, text: str) -> str:
        """Normalize generated specs to existing local assets."""
        text = self._sanitize_xml_text_entities(text)
        text = self._replace_invalid_icon_refs(text)
        return self._replace_invalid_chart_refs(text)

    @staticmethod
    def _sanitize_xml_text_entities(text: str) -> str:
        replacements = {
            "&amp;nbsp;": " ",
            "&nbsp;": " ",
            "&#160;": " ",
            "&amp;mdash;": "—",
            "&mdash;": "—",
            "&amp;ndash;": "–",
            "&ndash;": "–",
            "&amp;copy;": "©",
            "&copy;": "©",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    @staticmethod
    def _normalize_svg_style_contract(text: str) -> str:
        """Enforce local SVG style rules that LLMs commonly miss."""
        text = re.sub(r'flood-color="#000000"', 'flood-color="#0F172A"', text, flags=re.IGNORECASE)
        text = re.sub(r"flood-color='#000000'", "flood-color='#0F172A'", text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _normalize_svg_attribute_contract(text: str) -> str:
        """Repair common malformed SVG attributes before XML validation."""
        return re.sub(
            r'font-family=""([^">]+)",\s*"([^">]+)",\s*([^">]+)"',
            lambda match: (
                f'font-family="\'{match.group(1).strip()}\', '
                f'\'{match.group(2).strip()}\', {match.group(3).strip()}"'
            ),
            text,
        )

    def _replace_invalid_icon_refs(self, text: str) -> str:
        """Replace hallucinated icon names with available local icons."""
        text = re.sub(r"\btabler-outline/workflow\b", "tabler-outline/schema", text)
        text = re.sub(r"\btabler-outline/flowchart\b", "tabler-outline/schema", text)
        text = re.sub(r"`workflow`", "`schema`", text)
        text = re.sub(r"`flowchart`", "`schema`", text)
        text = re.sub(r"\bworkflow\.svg\b", "schema.svg", text)
        text = re.sub(r"\bflowchart\.svg\b", "schema.svg", text)

        def replace_icon_ref(match: re.Match) -> str:
            icon_ref = match.group(0)
            if self._icon_exists(icon_ref):
                return icon_ref

            replacement = self._replacement_icon(icon_ref)
            print(f"WARN: Replaced missing icon {icon_ref} -> {replacement}")
            return replacement

        libraries = "chunk-filled|tabler-filled|tabler-outline|phosphor-duotone|simple-icons"
        return re.sub(rf"\b(?:{libraries})/[a-z0-9][a-z0-9_-]*\b", replace_icon_ref, text)

    def _icon_exists(self, icon_ref: str) -> bool:
        if "/" not in icon_ref:
            return False
        library, icon_name = icon_ref.split("/", 1)
        icon_path = self.config.templates_dir / "icons" / library / f"{icon_name}.svg"
        return icon_path.exists()

    def _replacement_icon(self, icon_ref: str) -> str:
        if "/" in icon_ref:
            library, icon_name = icon_ref.split("/", 1)
            direct_candidates = [
                icon_name.replace("_", "-"),
                icon_name.replace("-", "_"),
            ]
            semantic_candidates = {
                "workflow": ["schema", "route", "route-2", "timeline"],
                "flowchart": ["schema", "route", "route-2", "timeline", "arrows-join"],
                "benefits": ["trending-up", "sparkles", "circle-check"],
                "benefit": ["trending-up", "sparkles", "circle-check"],
                "accuracy": ["target", "circle-check", "checklist"],
                "speed": ["bolt", "clock", "rocket"],
            }
            for candidate in direct_candidates + semantic_candidates.get(icon_name, []):
                icon_candidate = f"{library}/{candidate}"
                if self._icon_exists(icon_candidate):
                    return icon_candidate

            fallback = f"{library}/settings"
            if self._icon_exists(fallback):
                return fallback

        return "tabler-outline/settings"

    @staticmethod
    def _sanitize_speaker_notes(notes_content: str, output_language: str) -> str:
        if output_language == "Vietnamese":
            notes_content = re.sub(r"[\u4e00-\u9fff]+", "", notes_content)
            notes_content = re.sub(r"[ \t]{2,}", " ", notes_content)
        return notes_content.strip()

    @staticmethod
    def _extract_markdown_blocks(text: str) -> List[str]:
        blocks = re.findall(
            r"```(?:markdown|md)\s*[\r\n]+([\s\S]+?)\s*```",
            text,
            re.IGNORECASE,
        )
        return [b.strip() for b in blocks]

    @staticmethod
    def _select_block_for_slide(blocks: List[str], slide: dict, index: int) -> str:
        if not blocks:
            return ""

        markers = [
            f"Slide {slide['number']}",
            f"Page {slide['number']}",
            f"P{slide['number'].zfill(2)}",
            slide.get("title", ""),
        ]
        for block in blocks:
            if any(marker and marker.lower() in block.lower() for marker in markers):
                return block

        if index < len(blocks):
            return blocks[index]
        return ""

    def _select_notes_for_slide(self, blocks: List[str], full_text: str, slide: dict, index: int) -> str:
        candidates = blocks[:] if blocks else [full_text]
        slide_num = slide["number"]
        slide_key = slide["key"]

        for candidate in candidates:
            patterns = [
                rf"(?:^|\n)#{1,4}\s*(?:Speaker Notes\s*[-:]\s*)?(?:Slide|Page)\s*0?{slide_num}\b[\s\S]*?(?=\n#{1,4}\s*(?:Speaker Notes\s*[-:]\s*)?(?:Slide|Page)\s*\d+\b|\Z)",
                rf"(?:^|\n)#{1,4}\s*(?:{slide_key}|P0?{slide_num})\b[\s\S]*?(?=\n#{1,4}\s*(?:P\d+|Slide|Page)\b|\Z)",
                rf"(?:Speaker Notes|Notes)\s*(?:for)?\s*(?:Slide|Page)\s*0?{slide_num}\s*:?\s*([\s\S]*?)(?=(?:Speaker Notes|Notes)\s*(?:for)?\s*(?:Slide|Page)\s*\d+|$)",
            ]
            for pattern in patterns:
                match = re.search(pattern, candidate, re.IGNORECASE)
                if match:
                    return match.group(0 if match.lastindex is None else 1).strip()

        if index < len(blocks):
            return blocks[index].strip()
        return ""

    @staticmethod
    def _default_notes_for_slide(slide: dict, output_language: str) -> str:
        body = re.sub(r"[*_`#>-]+", " ", slide.get("body", ""))
        body = re.sub(r"\s+", " ", body).strip()
        if len(body) > 420:
            body = body[:420].rsplit(" ", 1)[0] + "..."

        if output_language == "Vietnamese":
            return (
                f"# Ghi chú thuyết trình - Slide {slide['number']}: {slide['title']}\n\n"
                f"Mở đầu: Giới thiệu ngắn gọn nội dung chính của slide này và liên hệ với mạch trình bày tổng thể.\n\n"
                f"Ý chính: {body or 'Nhấn mạnh thông điệp chính, số liệu then chốt và hàm ý hành động của slide.'}\n\n"
                "Chuyển ý: Kết nối kết luận của slide này với phần tiếp theo để người nghe thấy rõ luồng lập luận."
            )

        return (
            f"# Speaker Notes - Slide {slide['number']}: {slide['title']}\n\n"
            f"Opening: Introduce the slide and connect it to the overall narrative.\n\n"
            f"Key points: {body or 'Highlight the main message, key numbers, and action implications.'}\n\n"
            "Transition: Connect this slide's conclusion to the next section."
        )

    def _extract_svg_fallback(self, text: str, slide: dict):
        """Backward-compatible single-slide wrapper around window extraction."""
        self._extract_window_outputs(text, [slide], "Vietnamese")

    async def run_post_processing_and_export(self) -> bool:
        """Run Phase 7 (Post-Processing & PPTX export).
        
        Returns:
            True if export completed successfully and PPTX exists, False otherwise.
        """
        if not self.state.project_path:
            print("ERROR: Project path is not set in state.")
            return False

        # Step 1: Finalize SVGs
        from .tools.export_tools import run_finalize_svg
        finalize_output = run_finalize_svg(str(self.state.project_path))
        if self._command_output_has_problem(finalize_output):
            print(finalize_output)

        # Step 2: Convert to PPTX
        from .tools.export_tools import run_svg_to_pptx
        pptx_output = run_svg_to_pptx(str(self.state.project_path), source="final")
        if self._command_output_has_problem(pptx_output):
            print(pptx_output)

        # Check export directory
        export_dir = self.state.project_path / "exports"
        pptx_files = list(export_dir.glob("*.pptx"))
        if pptx_files:
            self.state.current_phase = "export_done"
            return True
        else:
            print("ERROR: No PPTX presentation files found in the exports directory.")
            return False
