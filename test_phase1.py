"""
Phase 1 Test Script
Verify all components are working
"""

import sys
from pathlib import Path

def test_imports():
    """Test that all required modules can be imported"""
    print("Testing imports...")
    
    try:
        import yaml
        print("  ✓ PyYAML")
    except ImportError:
        print("  ✗ PyYAML - Install with: pip install PyYAML")
        return False
    
    try:
        from PyQt6.QtWidgets import QApplication
        print("  ✓ PyQt6")
    except ImportError:
        print("  ✗ PyQt6 - Install with: pip install PyQt6")
        return False
    
    try:
        import RPi.GPIO as GPIO
        print("  ✓ RPi.GPIO (hardware mode)")
    except (ImportError, RuntimeError):
        print("  ⚠ RPi.GPIO not available (simulation mode)")
    
    return True


def test_config():
    """Test configuration file"""
    print("\nTesting configuration...")
    
    config_file = Path("config.yaml")
    if not config_file.exists():
        print("  ✗ config.yaml not found")
        return False
    
    try:
        import yaml
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Check required keys
        required_keys = ['sensor', 'logging', 'ui']
        for key in required_keys:
            if key not in config:
                print(f"  ✗ Missing key in config: {key}")
                return False
        
        print("  ✓ Configuration file valid")
        return True
        
    except Exception as e:
        print(f"  ✗ Error loading config: {e}")
        return False


def test_directories():
    """Test required directories exist"""
    print("\nTesting directories...")
    
    required_dirs = [
        Path("src"),
        Path("data/csv"),
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        if dir_path.exists():
            print(f"  ✓ {dir_path}")
        else:
            print(f"  ✗ {dir_path} - Creating...")
            dir_path.mkdir(parents=True, exist_ok=True)
            all_exist = False
    
    return True


def test_modules():
    """Test that all source modules can be imported"""
    print("\nTesting source modules...")
    
    # Add src to path
    sys.path.insert(0, str(Path("src").absolute()))
    
    modules = [
        ("sensor_reader", "SensorReader"),
        ("csv_logger", "CSVLogger"),
        ("simple_ui", "SensorMonitorWindow"),
        ("main", "SensorMonitorApp"),
    ]
    
    all_ok = True
    for module_name, class_name in modules:
        try:
            module = __import__(module_name)
            if hasattr(module, class_name):
                print(f"  ✓ {module_name}.{class_name}")
            else:
                print(f"  ✗ {module_name}.{class_name} not found")
                all_ok = False
        except Exception as e:
            print(f"  ✗ {module_name}: {e}")
            all_ok = False
    
    return all_ok


def test_sensor_reader():
    """Test sensor reader initialization"""
    print("\nTesting sensor reader...")
    
    try:
        sys.path.insert(0, str(Path("src").absolute()))
        import yaml
        from sensor_reader import SensorReader
        
        with open("config.yaml", 'r') as f:
            config = yaml.safe_load(f)
        
        reader = SensorReader(config)
        
        if reader.is_initialized:
            print("  ✓ Sensor reader initialized")
            
            # Test reading
            state = reader.read()
            print(f"  ✓ Sensor read: {state}")
            
            reader.cleanup()
            return True
        else:
            print("  ✗ Sensor reader failed to initialize")
            return False
            
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_csv_logger():
    """Test CSV logger"""
    print("\nTesting CSV logger...")
    
    try:
        sys.path.insert(0, str(Path("src").absolute()))
        import yaml
        from csv_logger import CSVLogger
        
        with open("config.yaml", 'r') as f:
            config = yaml.safe_load(f)
        
        logger = CSVLogger(config)
        
        # Start logging
        if logger.start_logging():
            print("  ✓ CSV logger started")
            
            # Log some data
            logger.log(True)
            logger.log(False)
            print("  ✓ Data logged")
            
            # Stop logging
            logger.stop_logging()
            print("  ✓ CSV logger stopped")
            
            return True
        else:
            print("  ✗ Failed to start logging")
            return False
            
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("Phase 1 Component Test")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("Directories", test_directories),
        ("Modules", test_modules),
        ("Sensor Reader", test_sensor_reader),
        ("CSV Logger", test_csv_logger),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! Ready to run Phase 1.")
        print("\nRun the application with:")
        print("  python src/main.py")
        return 0
    else:
        print("\n✗ Some tests failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

# Made with Bob
