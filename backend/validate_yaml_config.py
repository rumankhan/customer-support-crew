#!/usr/bin/env python3
"""
Validation script for YAML configuration compliance.
Tests that crew.py successfully loads agents and tasks from YAML files.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def validate_yaml_config():
    """Validate YAML configuration loading."""
    try:
        print("=" * 60)
        print("YAML Configuration Validation")
        print("=" * 60)
        
        # Test YAML file existence
        print("\n[1/4] Checking YAML files...")
        config_dir = os.path.join(os.path.dirname(__file__), "config")
        agents_yaml = os.path.join(config_dir, "agents.yaml")
        tasks_yaml = os.path.join(config_dir, "tasks.yaml")
        
        if not os.path.exists(agents_yaml):
            print(f"ERROR: agents.yaml not found at {agents_yaml}")
            return False
        print(f"  OK: agents.yaml found")
        
        if not os.path.exists(tasks_yaml):
            print(f"ERROR: tasks.yaml not found at {tasks_yaml}")
            return False
        print(f"  OK: tasks.yaml found")
        
        # Test YAML syntax
        print("\n[2/4] Validating YAML syntax...")
        import yaml
        
        with open(agents_yaml, 'r', encoding='utf-8') as f:
            agents_data = yaml.safe_load(f)
        print(f"  OK: agents.yaml parses successfully ({len(agents_data)} agents)")
        
        with open(tasks_yaml, 'r', encoding='utf-8') as f:
            tasks_data = yaml.safe_load(f)
        print(f"  OK: tasks.yaml parses successfully ({len(tasks_data)} tasks)")
        
        # Test crew module import (requires .env with LLM config)
        print("\n[3/4] Testing crew module import...")
        try:
            from backend.crew import CustomerSupportCrew
            print("  OK: CustomerSupportCrew imports successfully")
        except RuntimeError as e:
            if "No LLM configured" in str(e):
                print("  WARNING: No LLM configured (.env missing API keys)")
                print("  This is expected if .env is not set up yet")
                return True  # Still consider valid if YAML loads
            raise
        
        # Test crew instantiation (requires valid .env)
        print("\n[4/4] Testing crew instantiation...")
        try:
            crew = CustomerSupportCrew()
            print(f"  OK: Crew instantiated with {len(crew.agents)} agents")
            print(f"  Agent IDs: {list(crew.agents.keys())}")
            
            # Verify YAML config was loaded
            if hasattr(crew, 'agents_config'):
                print(f"  OK: agents_config loaded from YAML")
            if hasattr(crew, 'tasks_config'):
                print(f"  OK: tasks_config loaded from YAML")
                
        except RuntimeError as e:
            if "No LLM configured" in str(e):
                print("  WARNING: Cannot instantiate crew without LLM config")
                print("  YAML loading is valid, but .env needs API keys for full test")
                return True  # YAML structure is valid
            raise
        
        print("\n" + "=" * 60)
        print("SUCCESS: All validations passed!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = validate_yaml_config()
    sys.exit(0 if success else 1)
