#!/usr/bin/env python3
"""
gem5-SALAM Experiment Monitor
Generates an HTML dashboard showing experiment progress and statistics.

Usage:
    ./tools/experiment_monitor.py [OUTPUT_DIR] [--watch] [--interval SECONDS]
    
Examples:
    ./tools/experiment_monitor.py BM_ARM_OUT/all_benchmarks_20251229_230316
    ./tools/experiment_monitor.py BM_ARM_OUT/all_benchmarks_20251229_230316 --watch
    ./tools/experiment_monitor.py --latest --watch --interval 5
"""

import os
import sys
import glob
import time
import argparse
import re
import subprocess
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# HTML template with auto-refresh
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="{refresh_interval}">
    <title>gem5-SALAM Experiment Monitor</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e; 
            color: #eee;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1600px; margin: 0 auto; }}
        h1 {{ 
            color: #00d4ff; 
            margin-bottom: 10px;
            font-size: 2em;
        }}
        .timestamp {{ color: #888; margin-bottom: 20px; font-size: 0.9em; }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            border: 1px solid #0f3460;
        }}
        .summary-card .value {{
            font-size: 2.5em;
            font-weight: bold;
            color: #00d4ff;
        }}
        .summary-card .label {{ color: #888; margin-top: 5px; }}
        .summary-card.running .value {{ color: #ffd700; }}
        .summary-card.completed .value {{ color: #00ff88; }}
        .summary-card.failed .value {{ color: #ff4757; }}
        .summary-card.pending .value {{ color: #888; }}
        
        .section {{ margin-bottom: 30px; }}
        .section h2 {{ 
            color: #00d4ff; 
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #0f3460;
        }}
        
        table {{ 
            width: 100%; 
            border-collapse: collapse;
            background: #16213e;
            border-radius: 10px;
            overflow: hidden;
        }}
        th, td {{ 
            padding: 12px 15px; 
            text-align: left;
            border-bottom: 1px solid #0f3460;
        }}
        th {{ 
            background: #0f3460;
            color: #00d4ff;
            font-weight: 600;
        }}
        tr:hover {{ background: #1a2744; }}
        
        .status {{
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 500;
        }}
        .status.running {{ background: #ffd70033; color: #ffd700; }}
        .status.completed {{ background: #00ff8833; color: #00ff88; }}
        .status.failed {{ background: #ff475733; color: #ff4757; }}
        .status.pending {{ background: #88888833; color: #888; }}
        
        .progress-bar {{
            width: 100%;
            height: 8px;
            background: #0f3460;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 5px;
        }}
        .progress-bar .fill {{
            height: 100%;
            background: linear-gradient(90deg, #00d4ff, #00ff88);
            transition: width 0.3s;
        }}
        
        .latency {{ font-family: monospace; color: #ffd700; }}
        .ticks {{ font-family: monospace; color: #00ff88; }}
        .time {{ font-family: monospace; color: #00d4ff; }}
        .overhead {{ font-family: monospace; }}
        .overhead.positive {{ color: #ff4757; }}
        .overhead.zero {{ color: #00ff88; }}
        
        .benchmark-group {{
            background: #16213e;
            border-radius: 10px;
            margin-bottom: 15px;
            overflow: hidden;
            border: 1px solid #0f3460;
        }}
        .benchmark-header {{
            background: #0f3460;
            padding: 15px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .benchmark-header h3 {{ color: #00d4ff; }}
        .benchmark-content {{ 
            display: grid;
            grid-template-columns: 1fr 400px;
            gap: 20px;
            padding: 15px;
        }}
        .benchmark-experiments {{ }}
        .benchmark-chart {{
            background: #1a1a2e;
            border-radius: 8px;
            padding: 10px;
            min-height: 250px;
        }}
        
        .exp-row {{
            display: grid;
            grid-template-columns: 150px 100px 150px 120px 100px 1fr;
            gap: 10px;
            padding: 10px 15px;
            align-items: center;
            border-bottom: 1px solid #0f3460;
            font-size: 0.9em;
        }}
        .exp-row:last-child {{ border-bottom: none; }}
        .exp-row.header {{
            background: #0f346033;
            font-weight: 600;
            color: #00d4ff;
        }}
        
        .no-data {{ 
            text-align: center; 
            padding: 40px; 
            color: #888;
            font-style: italic;
        }}
        
        .running-processes {{
            background: #16213e;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            border: 1px solid #0f3460;
        }}
        .running-processes h3 {{ color: #ffd700; margin-bottom: 10px; }}
        .process-list {{ font-family: monospace; font-size: 0.9em; color: #aaa; }}
        
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(600px, 1fr));
            gap: 25px;
            margin-bottom: 30px;
        }}
        .chart-container {{
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            border: 1px solid #0f3460;
        }}
        .chart-container h3 {{
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 1.1em;
        }}
        .chart-wrapper {{
            height: 400px;
            position: relative;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔬 gem5-SALAM Experiment Monitor</h1>
        <div class="timestamp">
            Output Directory: <strong>{output_dir}</strong><br>
            Last Updated: {timestamp} (refreshes every {refresh_interval}s)
        </div>
        
        <div class="summary-grid">
            <div class="summary-card">
                <div class="value">{total_experiments}</div>
                <div class="label">Total Experiments</div>
            </div>
            <div class="summary-card completed">
                <div class="value">{completed}</div>
                <div class="label">Completed</div>
            </div>
            <div class="summary-card running">
                <div class="value">{running}</div>
                <div class="label">Running</div>
            </div>
            <div class="summary-card failed">
                <div class="value">{failed}</div>
                <div class="label">Failed</div>
            </div>
            <div class="summary-card pending">
                <div class="value">{pending}</div>
                <div class="label">Pending</div>
            </div>
        </div>
        
        <div class="section">
            <h2>Overall Progress</h2>
            <div class="progress-bar">
                <div class="fill" style="width: {progress_pct}%"></div>
            </div>
            <div style="text-align: center; margin-top: 10px; color: #888;">
                {progress_pct:.1f}% Complete ({completed_and_failed} / {total_experiments})
            </div>
        </div>
        
        {running_processes_html}
        
        <div class="section">
            <h2>📊 Performance Comparison Charts</h2>
            <div class="charts-grid">
                {charts_html}
            </div>
        </div>
        
        <div class="section">
            <h2>Experiments by Benchmark</h2>
            {benchmark_details}
        </div>
        
        <div class="section">
            <h2>Completed Results Summary</h2>
            {results_table}
        </div>
    </div>
    
    <script>
    {charts_js}
    </script>
</body>
</html>
"""

def get_running_gem5_processes():
    """Get list of running gem5 processes."""
    try:
        result = subprocess.run(
            ['ps', 'aux'], capture_output=True, text=True, timeout=5
        )
        processes = []
        for line in result.stdout.split('\n'):
            if 'gem5' in line and 'grep' not in line:
                parts = line.split()
                if len(parts) >= 11:
                    pid = parts[1]
                    cpu = parts[2]
                    mem = parts[3]
                    # Extract output directory from command
                    outdir_match = re.search(r'--outdir=(\S+)', line)
                    outdir = outdir_match.group(1) if outdir_match else 'unknown'
                    processes.append({
                        'pid': pid,
                        'cpu': cpu,
                        'mem': mem,
                        'outdir': outdir
                    })
        return processes
    except Exception:
        return []

def parse_stats_file(stats_path):
    """Parse a gem5 stats.txt file and extract key metrics."""
    stats = {}
    try:
        with open(stats_path, 'r') as f:
            content = f.read()
            
        # Extract key metrics from stats.txt
        patterns = {
            'simTicks': r'^simTicks\s+(\d+)',
            'simSeconds': r'^simSeconds\s+([\d.e+-]+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                stats[key] = match.group(1)
                
    except Exception as e:
        stats['error'] = str(e)
        
    return stats

def parse_run_log_stats(log_path):
    """Parse run.log to extract validation statistics.
    
    Sums statistics across ALL accelerators in the log file.
    """
    stats = {}
    try:
        with open(log_path, 'r') as f:
            content = f.read()
        
        # Sum all occurrences of validation stats across all accelerators
        # These stats appear in each accelerator's output section
        sum_patterns = {
            'kernelValidationRequests': r'Total validation requests:\s+(\d+)',
            'validationCacheHits': r'Validation cache hits:\s+(\d+)',
            'validationsDenied': r'Validations denied:\s+(\d+)',
            'uniquePagesValidated': r'Unique pages validated \(total\):\s+(\d+)',
        }
        
        # Sum these values across all accelerators
        for key, pattern in sum_patterns.items():
            matches = re.findall(pattern, content)
            if matches:
                total = sum(int(m) for m in matches)
                stats[key] = str(total)
        
        # For latency, sum total validation latency (in microseconds)
        lat_matches = re.findall(r'Total validation latency:\s+([\d.]+)\s*us', content)
        if lat_matches:
            total_lat = sum(float(m) for m in lat_matches)
            stats['totalValidationLatency'] = f"{total_lat:.1f}"
        
        # Check if validation was enabled (just need one YES)
        if 'Kernel validation enabled:       YES' in content:
            stats['validationEnabled'] = 'YES'
        elif 'Kernel validation enabled:       NO' in content:
            stats['validationEnabled'] = 'NO'
        
        # Calculate combined cache hit rate if we have the data
        if 'kernelValidationRequests' in stats and 'validationCacheHits' in stats:
            requests = int(stats['kernelValidationRequests'])
            hits = int(stats['validationCacheHits'])
            if requests + hits > 0:
                stats['validationCacheHitRate'] = f"{hits / (requests + hits) * 100:.1f}%"
                
    except Exception as e:
        pass
        
    return stats

def parse_run_log(log_path):
    """Parse run.log to determine experiment status."""
    try:
        with open(log_path, 'r') as f:
            content = f.read()
            
        if 'Exiting @' in content and 'm5_exit' in content:
            return 'completed', None
        elif 'panic:' in content or 'fatal:' in content:
            # Extract error message
            error_match = re.search(r'(panic:|fatal:)(.+?)(?:\n|$)', content)
            error_msg = error_match.group(2).strip() if error_match else 'Unknown error'
            return 'failed', error_msg[:100]
        elif content.strip():
            # Log exists with content but not finished
            return 'running', None
        else:
            return 'pending', None
    except FileNotFoundError:
        return 'pending', None
    except Exception as e:
        return 'unknown', str(e)

def get_experiment_info(exp_dir):
    """Get information about a single experiment."""
    info = {
        'dir': exp_dir,
        'name': os.path.basename(exp_dir),
        'status': 'pending',
        'error': None,
        'stats': {},
        'latency': 0,
    }
    
    # Parse latency from directory name
    dirname = os.path.basename(exp_dir)
    if 'baseline' in dirname:
        info['latency'] = 0
    else:
        lat_match = re.search(r'latency_(\d+)', dirname)
        if lat_match:
            info['latency'] = int(lat_match.group(1))
    
    # Check run.log for status
    run_log = os.path.join(exp_dir, 'run.log')
    info['status'], info['error'] = parse_run_log(run_log)
    
    # Parse stats from stats.txt
    stats_file = os.path.join(exp_dir, 'stats.txt')
    if os.path.exists(stats_file):
        info['stats'] = parse_stats_file(stats_file)
        if info['stats'] and 'simTicks' in info['stats']:
            info['status'] = 'completed'
    
    # Parse validation stats from run.log (they are printed there, not in stats.txt)
    if os.path.exists(run_log):
        validation_stats = parse_run_log_stats(run_log)
        info['stats'].update(validation_stats)
    
    return info

def scan_output_directory(output_dir, expected_benchmarks=None, expected_latencies=None):
    """Scan the output directory and collect all experiment information.
    
    Args:
        output_dir: Path to output directory
        expected_benchmarks: List of expected benchmark names (for showing pending)
        expected_latencies: List of expected latency values (for showing pending)
    """
    experiments = defaultdict(list)
    
    if not os.path.exists(output_dir):
        return experiments
    
    # Check if this is a single benchmark or all benchmarks run
    subdirs = [d for d in os.listdir(output_dir) 
               if os.path.isdir(os.path.join(output_dir, d))]
    
    # Track which experiments we've found
    found_experiments = set()
    
    # Determine structure
    is_all_benchmarks = False
    for subdir in subdirs:
        subdir_path = os.path.join(output_dir, subdir)
        
        # Check if this is a benchmark directory or experiment directory
        if 'baseline' in subdir or 'latency_' in subdir:
            # Single benchmark mode - experiments directly under output_dir
            exp_info = get_experiment_info(subdir_path)
            experiments['default'].append(exp_info)
            found_experiments.add(('default', exp_info['latency']))
        else:
            is_all_benchmarks = True
            # All benchmarks mode - subdir is benchmark name
            for exp_subdir in os.listdir(subdir_path):
                exp_path = os.path.join(subdir_path, exp_subdir)
                if os.path.isdir(exp_path):
                    exp_info = get_experiment_info(exp_path)
                    experiments[subdir].append(exp_info)
                    found_experiments.add((subdir, exp_info['latency']))
    
    # Add pending experiments for expected benchmarks/latencies that haven't started
    if is_all_benchmarks and expected_benchmarks and expected_latencies:
        for bench in expected_benchmarks:
            for lat in expected_latencies:
                if (bench, lat) not in found_experiments:
                    # Create pending experiment entry
                    if lat == 0:
                        exp_name = 'baseline_no_validation'
                    else:
                        exp_name = f'latency_{lat}'
                    exp_info = {
                        'dir': os.path.join(output_dir, bench, exp_name),
                        'name': exp_name,
                        'status': 'pending',
                        'error': None,
                        'stats': {},
                        'latency': lat,
                    }
                    experiments[bench].append(exp_info)
    
    # Sort experiments by latency
    for bench in experiments:
        experiments[bench].sort(key=lambda x: x['latency'])
    
    return experiments

def format_ticks(ticks_str):
    """Format tick count for display."""
    try:
        ticks = int(ticks_str)
        if ticks >= 1e12:
            return f"{ticks/1e12:.2f}T"
        elif ticks >= 1e9:
            return f"{ticks/1e9:.2f}G"
        elif ticks >= 1e6:
            return f"{ticks/1e6:.2f}M"
        elif ticks >= 1e3:
            return f"{ticks/1e3:.2f}K"
        return str(ticks)
    except:
        return ticks_str

def format_latency(latency):
    """Format latency value for display."""
    if latency == 0:
        return "No validation"
    elif latency >= 1000000:
        return f"{latency/1000000:.1f}M cycles"
    elif latency >= 1000:
        return f"{latency/1000:.0f}K cycles"
    return f"{latency} cycles"

def format_sim_time(sim_seconds_str):
    """Format simulation time for display with appropriate units."""
    try:
        secs = float(sim_seconds_str)
        if secs >= 1:
            return f"{secs:.4f} s"
        elif secs >= 1e-3:
            return f"{secs*1e3:.4f} ms"
        elif secs >= 1e-6:
            return f"{secs*1e6:.4f} µs"
        elif secs >= 1e-9:
            return f"{secs*1e9:.4f} ns"
        else:
            return f"{secs:.6e} s"
    except:
        return sim_seconds_str

def calculate_overhead(baseline_secs, current_secs):
    """Calculate overhead percentage compared to baseline."""
    try:
        baseline = float(baseline_secs)
        current = float(current_secs)
        if baseline > 0:
            overhead = ((current - baseline) / baseline) * 100
            return overhead
        return 0
    except:
        return None

def generate_chart_data(experiments):
    """Generate chart data for each benchmark."""
    chart_data = {}
    
    for bench, exps in experiments.items():
        if bench == 'default':
            continue
            
        # Get completed experiments with sim time data
        completed_exps = [e for e in exps if e['status'] == 'completed' and e['stats'].get('simSeconds')]
        if not completed_exps:
            continue
        
        # Sort by latency
        completed_exps.sort(key=lambda x: x['latency'])
        
        # Find baseline (latency=0)
        baseline_time = None
        for exp in completed_exps:
            if exp['latency'] == 0:
                baseline_time = float(exp['stats']['simSeconds'])
                break
        
        # Build data points
        labels = []
        times = []
        overheads = []  # Overhead relative to baseline (0% = baseline)
        
        for exp in completed_exps:
            lat = exp['latency']
            sim_secs = float(exp['stats']['simSeconds'])
            
            if lat == 0:
                labels.append('Baseline')
            elif lat >= 1000000:
                labels.append(f"{lat/1000000:.0f}M")
            elif lat >= 1000:
                labels.append(f"{lat/1000:.0f}K")
            else:
                labels.append(str(lat))
            
            times.append(sim_secs)
            
            # Calculate overhead relative to baseline (0% = baseline time)
            if baseline_time and baseline_time > 0:
                overhead = ((sim_secs - baseline_time) / baseline_time) * 100
                overheads.append(overhead)
            else:
                overheads.append(0)  # Default to 0% if no baseline
        
        chart_data[bench] = {
            'labels': labels,
            'times': times,
            'overheads': overheads,  # Overhead % (0% = baseline)
            'baseline_time': baseline_time
        }
    
    return chart_data

def generate_html(output_dir, experiments, refresh_interval=10):
    """Generate the HTML dashboard."""
    
    # Calculate summary stats
    total = 0
    completed = 0
    running = 0
    failed = 0
    pending = 0
    
    for bench, exps in experiments.items():
        for exp in exps:
            total += 1
            if exp['status'] == 'completed':
                completed += 1
            elif exp['status'] == 'running':
                running += 1
            elif exp['status'] == 'failed':
                failed += 1
            else:
                pending += 1
    
    completed_and_failed = completed + failed
    progress_pct = (completed_and_failed / total * 100) if total > 0 else 0
    
    # Generate running processes HTML
    processes = get_running_gem5_processes()
    if processes:
        proc_html = '<div class="running-processes"><h3>🔄 Running gem5 Processes</h3><div class="process-list">'
        for p in processes:
            proc_html += f"PID {p['pid']} | CPU: {p['cpu']}% | MEM: {p['mem']}% | {os.path.basename(p['outdir'])}<br>"
        proc_html += '</div></div>'
    else:
        proc_html = ''
    
    # Generate chart data
    chart_data = generate_chart_data(experiments)
    
    # Generate charts HTML and JS
    charts_html = ''
    charts_js = ''
    chart_idx = 0
    
    for bench in sorted(chart_data.keys()):
        data = chart_data[bench]
        if len(data['times']) < 2:
            continue
        
        chart_id = f"chart_{chart_idx}"
        chart_idx += 1
        
        # Calculate baseline time in ms for display
        baseline_ms = data['baseline_time'] * 1000 if data['baseline_time'] else 0
        
        charts_html += f'''
        <div class="chart-container">
            <h3>{bench} - Overhead vs Baseline (baseline = {baseline_ms:.4f} ms)</h3>
            <div class="chart-wrapper">
                <canvas id="{chart_id}"></canvas>
            </div>
        </div>
        '''
        
        # Generate Chart.js code - show overhead where baseline = 0%
        labels_json = str(data['labels']).replace("'", '"')
        overheads_json = str([round(o, 2) for o in data['overheads']])
        
        # Calculate max overhead for axis scaling
        max_overhead = max(data['overheads']) if data['overheads'] else 10
        y_max = max(5, max_overhead * 1.2)  # 20% padding above max value
        
        charts_js += f'''
        new Chart(document.getElementById('{chart_id}'), {{
            type: 'bar',
            data: {{
                labels: {labels_json},
                datasets: [{{
                    label: 'Overhead (%)',
                    data: {overheads_json},
                    backgroundColor: function(context) {{
                        const value = context.raw;
                        if (value <= 0) return 'rgba(0, 255, 136, 0.8)';
                        else if (value <= 5) return 'rgba(255, 215, 0, 0.8)';
                        else return 'rgba(255, 71, 87, 0.8)';
                    }},
                    borderColor: function(context) {{
                        const value = context.raw;
                        if (value <= 0) return 'rgba(0, 255, 136, 1)';
                        else if (value <= 5) return 'rgba(255, 215, 0, 1)';
                        else return 'rgba(255, 71, 87, 1)';
                    }},
                    borderWidth: 2,
                    borderRadius: 4,
                    barPercentage: 0.7
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                layout: {{
                    padding: {{ top: 20, bottom: 10 }}
                }},
                plugins: {{
                    legend: {{
                        display: false
                    }},
                    tooltip: {{
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        titleFont: {{ size: 14 }},
                        bodyFont: {{ size: 13 }},
                        padding: 12,
                        callbacks: {{
                            label: function(context) {{
                                const overhead = context.raw;
                                const sign = overhead >= 0 ? '+' : '';
                                return sign + overhead.toFixed(2) + '% overhead vs baseline';
                            }}
                        }}
                    }},
                    datalabels: {{
                        display: false
                    }}
                }},
                scales: {{
                    x: {{
                        title: {{ 
                            display: true, 
                            text: 'Validation Latency (cycles)', 
                            color: '#aaa',
                            font: {{ size: 13, weight: 'bold' }}
                        }},
                        ticks: {{ 
                            color: '#ccc',
                            font: {{ size: 12 }}
                        }},
                        grid: {{ color: 'rgba(15, 52, 96, 0.5)' }}
                    }},
                    y: {{
                        type: 'linear',
                        display: true,
                        position: 'left',
                        min: 0,
                        max: {y_max:.2f},
                        title: {{ 
                            display: true, 
                            text: 'Overhead (%)', 
                            color: '#00d4ff',
                            font: {{ size: 13, weight: 'bold' }}
                        }},
                        ticks: {{ 
                            color: '#00d4ff',
                            font: {{ size: 12 }},
                            stepSize: {y_max/5:.2f},
                            callback: function(value) {{ return '+' + value.toFixed(1) + '%'; }}
                        }},
                        grid: {{ 
                            color: 'rgba(15, 52, 96, 0.5)',
                            lineWidth: 1
                        }}
                    }}
                }}
            }}
        }});
        '''
    
    if not charts_html:
        charts_html = '<div class="no-data">No completed experiments with timing data yet</div>'
    
    # Generate benchmark details HTML with overhead info
    benchmark_html = ''
    for bench in sorted(experiments.keys()):
        exps = experiments[bench]
        if not exps:
            continue
        
        # Find baseline time for this benchmark
        baseline_time = None
        for exp in exps:
            if exp['latency'] == 0 and exp['status'] == 'completed' and exp['stats'].get('simSeconds'):
                baseline_time = float(exp['stats']['simSeconds'])
                break
            
        bench_completed = sum(1 for e in exps if e['status'] == 'completed')
        bench_total = len(exps)
        
        benchmark_html += f'''
        <div class="benchmark-group">
            <div class="benchmark-header">
                <h3>{bench if bench != 'default' else 'Benchmark'}</h3>
                <span>{bench_completed}/{bench_total} completed</span>
            </div>
            <div class="benchmark-experiments">
                <div class="exp-row header">
                    <div>Latency</div>
                    <div>Status</div>
                    <div>Sim Time</div>
                    <div>Overhead</div>
                    <div>Validations</div>
                    <div>Cache Rate</div>
                </div>
        '''
        
        for exp in exps:
            status_class = exp['status']
            latency_str = format_latency(exp['latency'])
            
            # Stats display
            if exp['stats'] and exp['stats'].get('simSeconds'):
                sim_time = format_sim_time(exp['stats']['simSeconds'])
                
                # Calculate overhead
                if baseline_time and exp['latency'] > 0:
                    current_time = float(exp['stats']['simSeconds'])
                    overhead = calculate_overhead(baseline_time, current_time)
                    if overhead is not None:
                        overhead_str = f"+{overhead:.2f}%" if overhead > 0 else f"{overhead:.2f}%"
                        overhead_class = "positive" if overhead > 0 else "zero"
                    else:
                        overhead_str = "N/A"
                        overhead_class = ""
                else:
                    overhead_str = "baseline" if exp['latency'] == 0 else "N/A"
                    overhead_class = "zero" if exp['latency'] == 0 else ""
                
                validations = exp['stats'].get('kernelValidationRequests', 'N/A')
                cache_rate = exp['stats'].get('validationCacheHitRate', 'N/A')
                
                # Check if validation was enabled
                val_enabled = exp['stats'].get('validationEnabled', 'NO')
                if val_enabled == 'NO' and exp['latency'] == 0:
                    validations = 'disabled'
                    cache_rate = '-'
            elif exp['error']:
                sim_time = '-'
                overhead_str = '-'
                overhead_class = ''
                validations = '-'
                cache_rate = '-'
            else:
                sim_time = '-'
                overhead_str = '-'
                overhead_class = ''
                validations = '-'
                cache_rate = '-'
            
            benchmark_html += f'''
                <div class="exp-row">
                    <div><span class="latency">{latency_str}</span></div>
                    <div><span class="status {status_class}">{status_class}</span></div>
                    <div><span class="time">{sim_time}</span></div>
                    <div><span class="overhead {overhead_class}">{overhead_str}</span></div>
                    <div>{validations}</div>
                    <div>{cache_rate}</div>
                </div>
            '''
        
        benchmark_html += '</div></div>'
    
    if not benchmark_html:
        benchmark_html = '<div class="no-data">No experiments found in output directory</div>'
    
    # Generate results table HTML with overhead
    results_rows = ''
    
    # Group by benchmark to calculate baseline
    for bench in sorted(experiments.keys()):
        bench_exps = experiments[bench]
        
        # Find baseline
        baseline_time = None
        for exp in bench_exps:
            if exp['latency'] == 0 and exp['status'] == 'completed' and exp['stats'].get('simSeconds'):
                baseline_time = float(exp['stats']['simSeconds'])
                break
        
        for exp in bench_exps:
            if exp['status'] == 'completed' and exp['stats']:
                bench_name = bench if bench != 'default' else 'benchmark'
                validations = exp['stats'].get('kernelValidationRequests', 'N/A')
                cache_rate = exp['stats'].get('validationCacheHitRate', 'N/A')
                sim_secs = exp['stats'].get('simSeconds', 'N/A')
                sim_time_fmt = format_sim_time(sim_secs)
                
                # Calculate overhead
                if baseline_time and exp['latency'] > 0 and sim_secs != 'N/A':
                    overhead = calculate_overhead(baseline_time, float(sim_secs))
                    if overhead is not None:
                        overhead_str = f"+{overhead:.2f}%"
                        overhead_class = "positive" if overhead > 0 else "zero"
                    else:
                        overhead_str = "N/A"
                        overhead_class = ""
                else:
                    overhead_str = "baseline" if exp['latency'] == 0 else "N/A"
                    overhead_class = "zero" if exp['latency'] == 0 else ""
                
                val_enabled = exp['stats'].get('validationEnabled', 'NO')
                if val_enabled == 'NO' and exp['latency'] == 0:
                    validations = 'disabled'
                    cache_rate = '-'
                    
                results_rows += f'''
                <tr>
                    <td>{bench_name}</td>
                    <td class="latency">{format_latency(exp['latency'])}</td>
                    <td class="time">{sim_time_fmt}</td>
                    <td class="overhead {overhead_class}">{overhead_str}</td>
                    <td>{validations}</td>
                    <td>{cache_rate}</td>
                </tr>
                '''
    
    if results_rows:
        results_table = f'''
        <table>
            <thead>
                <tr>
                    <th>Benchmark</th>
                    <th>Validation Latency</th>
                    <th>Sim Time</th>
                    <th>Overhead vs Baseline</th>
                    <th>Validations</th>
                    <th>Cache Hit Rate</th>
                </tr>
            </thead>
            <tbody>
                {results_rows}
            </tbody>
        </table>
        '''
    else:
        results_table = '<div class="no-data">No completed experiments with stats yet</div>'
    
    # Generate final HTML
    html = HTML_TEMPLATE.format(
        refresh_interval=refresh_interval,
        output_dir=output_dir,
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        total_experiments=total,
        completed=completed,
        running=running,
        failed=failed,
        pending=pending,
        progress_pct=progress_pct,
        completed_and_failed=completed_and_failed,
        running_processes_html=proc_html,
        charts_html=charts_html,
        charts_js=charts_js,
        benchmark_details=benchmark_html,
        results_table=results_table,
    )
    
    return html

def find_latest_output_dir(base_dir='BM_ARM_OUT'):
    """Find the most recently created output directory."""
    if not os.path.exists(base_dir):
        return None
    
    dirs = [os.path.join(base_dir, d) for d in os.listdir(base_dir)
            if os.path.isdir(os.path.join(base_dir, d))]
    
    if not dirs:
        return None
    
    return max(dirs, key=os.path.getctime)

# All available benchmarks in the system
AVAILABLE_BENCHMARKS = [
    'mobilenetv2', 'mobilenetv2_35', 'mobilenetv2_75',
    'lenet_a', 'lenet_b', 'lenet_c',
    'bfs', 'fft', 'gemm', 'md_grid', 'md_knn', 'nw', 
    'spmv', 'stencil2d', 'stencil3d', 'mergesort'
]

def detect_latencies_from_dir(output_dir):
    """Detect the latencies being used in the experiment from existing directories."""
    latencies = set()
    try:
        for bench_dir in os.listdir(output_dir):
            bench_path = os.path.join(output_dir, bench_dir)
            if os.path.isdir(bench_path):
                for exp_dir in os.listdir(bench_path):
                    if 'baseline' in exp_dir:
                        latencies.add(0)
                    else:
                        lat_match = re.search(r'latency_(\d+)', exp_dir)
                        if lat_match:
                            latencies.add(int(lat_match.group(1)))
    except Exception:
        pass
    return sorted(latencies) if latencies else [0]

def start_http_server(directory, port):
    """Start an HTTP server in the background serving the given directory."""
    import http.server
    import socketserver
    import threading
    
    # Use absolute path
    abs_directory = os.path.abspath(directory)
    
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=abs_directory, **kwargs)
        
        def log_message(self, format, *args):
            pass  # Suppress HTTP request logging
    
    try:
        httpd = socketserver.TCPServer(("", port), QuietHandler)
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"Port {port} is already in use - server may already be running")
            return None
        raise
    
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd

def main():
    parser = argparse.ArgumentParser(description='Monitor gem5-SALAM experiments')
    parser.add_argument('output_dir', nargs='?', help='Output directory to monitor')
    parser.add_argument('--latest', action='store_true', help='Use the latest output directory')
    parser.add_argument('--watch', '-w', action='store_true', help='Continuously update the HTML file')
    parser.add_argument('--interval', '-i', type=int, default=10, help='Refresh interval in seconds')
    parser.add_argument('--output', '-o', default='experiment_status.html', help='Output HTML file name')
    parser.add_argument('--benchmarks', '-b', help='Comma-separated list of expected benchmarks')
    parser.add_argument('--latencies', '-l', help='Comma-separated list of expected latencies')
    parser.add_argument('--serve', '-s', action='store_true', help='Start HTTP server and open browser')
    parser.add_argument('--port', '-p', type=int, default=8080, help='HTTP server port (default: 8080)')
    
    args = parser.parse_args()
    
    # Determine output directory
    if args.latest:
        output_dir = find_latest_output_dir()
        if not output_dir:
            print("Error: No output directories found in BM_ARM_OUT/")
            sys.exit(1)
        print(f"Using latest output directory: {output_dir}")
    elif args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = find_latest_output_dir()
        if not output_dir:
            print("Error: No output directory specified and none found in BM_ARM_OUT/")
            print("Usage: ./experiment_monitor.py <OUTPUT_DIR> [--watch]")
            sys.exit(1)
        print(f"Using latest output directory: {output_dir}")
    
    if not os.path.exists(output_dir):
        print(f"Error: Directory not found: {output_dir}")
        sys.exit(1)
    
    # Use absolute paths to avoid issues when server changes cwd
    output_dir = os.path.abspath(output_dir)
    html_file = os.path.join(output_dir, args.output)
    
    # Determine expected benchmarks and latencies
    if args.benchmarks:
        expected_benchmarks = [b.strip() for b in args.benchmarks.split(',')]
    elif 'all_benchmarks' in output_dir:
        expected_benchmarks = AVAILABLE_BENCHMARKS
    else:
        expected_benchmarks = None
    
    if args.latencies:
        expected_latencies = [int(l.strip()) for l in args.latencies.split(',')]
    else:
        # Auto-detect from existing experiments
        expected_latencies = detect_latencies_from_dir(output_dir)
    
    print(f"Monitoring: {output_dir}")
    print(f"HTML output: {html_file}")
    if expected_benchmarks:
        print(f"Expected benchmarks: {len(expected_benchmarks)}")
        print(f"Expected latencies: {expected_latencies}")
        print(f"Expected total experiments: {len(expected_benchmarks) * len(expected_latencies)}")
    
    # Generate initial HTML file before starting server
    experiments = scan_output_directory(output_dir, expected_benchmarks, expected_latencies)
    html = generate_html(output_dir, experiments, args.interval)
    with open(html_file, 'w') as f:
        f.write(html)
    print(f"Dashboard generated: {html_file}")
    
    # Start HTTP server if requested
    httpd = None
    dashboard_url = None
    if args.serve:
        httpd = start_http_server(output_dir, args.port)
        dashboard_url = f"http://localhost:{args.port}/{args.output}"
        if httpd:
            print(f"HTTP server started at http://localhost:{args.port}/")
            print(f"Dashboard URL: {dashboard_url}")
            # Open browser
            import webbrowser
            webbrowser.open(dashboard_url)
        else:
            # Server might already be running, still try to open browser
            dashboard_url = f"http://localhost:{args.port}/{args.output}"
            print(f"Trying to open: {dashboard_url}")
            import webbrowser
            webbrowser.open(dashboard_url)
    
    if args.watch:
        print(f"Watching for changes (Ctrl+C to stop)...")
        if not args.serve:
            print(f"Open {html_file} in a browser to view the dashboard")
        try:
            while True:
                experiments = scan_output_directory(output_dir, expected_benchmarks, expected_latencies)
                html = generate_html(output_dir, experiments, args.interval)
                with open(html_file, 'w') as f:
                    f.write(html)
                
                # Print summary to console
                total = sum(len(e) for e in experiments.values())
                completed = sum(1 for exps in experiments.values() for e in exps if e['status'] == 'completed')
                running = sum(1 for exps in experiments.values() for e in exps if e['status'] == 'running')
                failed = sum(1 for exps in experiments.values() for e in exps if e['status'] == 'failed')
                print(f"\r[{datetime.now().strftime('%H:%M:%S')}] Total: {total} | Completed: {completed} | Running: {running} | Failed: {failed}", end='', flush=True)
                
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped monitoring.")
    elif not args.serve:
        # Print summary if not watching and not serving
        total = sum(len(e) for e in experiments.values())
        completed = sum(1 for exps in experiments.values() for e in exps if e['status'] == 'completed')
        running = sum(1 for exps in experiments.values() for e in exps if e['status'] == 'running')
        failed = sum(1 for exps in experiments.values() for e in exps if e['status'] == 'failed')
        print(f"Summary: Total={total}, Completed={completed}, Running={running}, Failed={failed}")
    
    # If serving without watch, keep the server running
    if args.serve and not args.watch and httpd:
        total = sum(len(e) for e in experiments.values())
        completed = sum(1 for exps in experiments.values() for e in exps if e['status'] == 'completed')
        running = sum(1 for exps in experiments.values() for e in exps if e['status'] == 'running')
        failed = sum(1 for exps in experiments.values() for e in exps if e['status'] == 'failed')
        print(f"Summary: Total={total}, Completed={completed}, Running={running}, Failed={failed}")
        print(f"\nServer running at http://localhost:{args.port}/")
        print("Press Ctrl+C to stop...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nServer stopped.")

if __name__ == '__main__':
    main()
