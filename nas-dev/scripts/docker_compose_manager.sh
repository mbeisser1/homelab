#!/bin/bash

# Docker Compose Manager Script
set -u  # Exit on undefined variable

# Base directory containing docker compose projects
BASE_DIR="${HOME}/docker_compose"

# Array of projects to manage
PROJECTS=("backrest" "dockge" "immich" "jellyfin" "networking" "xwiki")

# Function to validate project directory
validate_project() {
    local project_dir="$1"
    local project_name="$2"

    if [[ ! -d "$project_dir" ]]; then
        echo "ERROR: Directory not found: $project_dir" >&2
        return 1
    fi

    if [[ ! -f "$project_dir/compose.yml" ]]; then
        echo "ERROR: compose.yml not found in $project_name" >&2
        return 1
    fi

    return 0
}

# Function to start all projects
start_all() {
    local failed=0
    echo "Starting all projects..."

    for project in "${PROJECTS[@]}"; do
        local project_dir="$BASE_DIR/$project"
        echo "Starting $project..."

        if validate_project "$project_dir" "$project"; then
            if cd "$project_dir" && docker compose -f compose.yml up -d 2>&1; then
                echo "SUCCESS: $project started"
            else
                echo "ERROR: Failed to start $project" >&2
                ((failed++))
            fi
        else
            ((failed++))
        fi
        echo ""
    done

    if [[ $failed -eq 0 ]]; then
        echo "All projects started successfully"
        return 0
    else
        echo "ERROR: $failed project(s) failed to start" >&2
        return 1
    fi
}

# Function to stop all projects
stop_all() {
    local failed=0
    echo "Stopping all projects..."

    for project in "${PROJECTS[@]}"; do
        local project_dir="$BASE_DIR/$project"
        echo "Stopping $project..."

        if validate_project "$project_dir" "$project"; then
            if cd "$project_dir" && docker compose -f compose.yml down 2>&1; then
                echo "SUCCESS: $project stopped"
            else
                echo "ERROR: Failed to stop $project" >&2
                ((failed++))
            fi
        else
            ((failed++))
        fi
        echo ""
    done

    if [[ $failed -eq 0 ]]; then
        echo "All projects stopped successfully"
        return 0
    else
        echo "ERROR: $failed project(s) failed to stop" >&2
        return 1
    fi
}

# Function to restart all projects
restart_all() {
    echo "Restarting all projects..."
    stop_all
    echo ""
    start_all
}

# Function to show status of all projects
status_all() {
    docker ps
}

# Display usage information
usage() {
    cat << EOF
Usage: $0 {start|stop|restart|status}

Commands:
    start    - Start all Docker Compose projects
    stop     - Stop all Docker Compose projects
    restart  - Restart all Docker Compose projects
    status   - Show status of all Docker Compose projects

Projects: ${PROJECTS[*]}
EOF
}

# Main script logic
main() {
    if [[ $# -eq 0 ]]; then
        usage
        exit 1
    fi

    local command="$1"

    case "$command" in
        start)
            start_all
            ;;
        stop)
            stop_all
            ;;
        restart)
            restart_all
            ;;
        status)
            status_all
            ;;
        *)
            echo "ERROR: Unknown command: $command" >&2
            usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
