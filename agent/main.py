"""
CLI Entry Point for PPT Master AI Agent System.

Usage:
    python3 -m agent.main <source_files_or_URLs...> [--format ppt169] [--model model_name] [--temperature temp]
"""

import sys
import asyncio
import argparse
from pathlib import Path

from .config import AgentConfig
from .state import ProjectState
from .orchestrator import PipelineOrchestrator


def parse_args():
    parser = argparse.ArgumentParser(description="PPT Master AI Agent System CLI")
    
    # Core input
    parser.add_argument(
        "sources", 
        nargs="+", 
        help="Source files (PDF, DOCX, XLSX, PPTX, MD, TXT) or web URLs to convert and import"
    )
    
    # Project preferences
    parser.add_argument(
        "--format", 
        default="ppt169", 
        help="Canvas format alias (ppt169, ppt43, xhs, story, etc.)"
    )
    
    # Model preferences
    parser.add_argument(
        "--model", 
        help="Name of the LLM model to run"
    )
    parser.add_argument(
        "--base-url", 
        help="Base API URL for the LLM server"
    )
    parser.add_argument(
        "--api-key", 
        help="API key for the LLM server"
    )
    parser.add_argument(
        "--temperature", 
        type=float, 
        help="Temperature parameter for sampling"
    )

    return parser.parse_args()


async def main_async():
    args = parse_args()
    
    # Read/override configurations
    config = AgentConfig.from_env()
    
    if args.model:
        config.model = args.model
    if args.base_url:
        config.base_url = args.base_url
    if args.api_key:
        config.api_key = args.api_key
    if args.temperature is not None:
        config.temperature = args.temperature

    print("=" * 80)
    print("         PPT MASTER AI AGENT SYSTEM - CLI INTERFACE")
    print("=" * 80)
    print(f"Model Endpoint:  {config.base_url}")
    print(f"Model ID:        {config.model}")
    print(f"Temperature:     {config.temperature}")
    print(f"Canvas Format:   {args.format}")
    print(f"Source Files:    {', '.join(args.sources)}")
    print("=" * 80)

    # Initialize shared project state
    state = ProjectState(
        source_files=args.sources,
        canvas_format=args.format,
    )
    
    # Run the orchestrator
    orchestrator = PipelineOrchestrator(state, config)
    
    try:
        success = await orchestrator.run_to_strategist()
        if success:
            print("\n🎉 Phase 2 Completed Successfully!")
            print(f"Design Specification:  {state.design_spec_path}")
            print(f"Execution Lock:        {state.spec_lock_path}")
            print("=" * 80)
            
            exec_success = await orchestrator.run_executor()
            if exec_success:
                print("\nPhase 3 (SVG Generation & Notes) completed successfully.")
                print(f"SVGs Directory:  {state.svg_output_dir}")
                print(f"Notes Directory: {state.notes_dir}")
                print("=" * 80)
                
                export_success = await orchestrator.run_post_processing_and_export()
                if export_success:
                    print("\nPhase 4 (Post-processing & PPTX Export) completed successfully.")
                    print("=" * 80)
                else:
                    print("\nPhase 4 (Post-processing & PPTX Export) failed.")
                    sys.exit(1)
            else:
                print("\nPhase 3 (SVG Generation) failed.")
                sys.exit(1)
        else:
            print("\nPhase 2 failed to finalize planning specs.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\nExecution cancelled by user.")
        sys.exit(0)
    except Exception as e:
        import traceback
        print(f"\nUNEXPECTED SYSTEM ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
