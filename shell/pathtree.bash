# PathTree Bash Integration
# To use, add 'source /path/to/pathtree.bash' to your ~/.bashrc

pb() {
    # Use only function-local variables
    local temp_file
    local exit_status
    local target_path
    local cd_status

    temp_file=$(mktemp 2>/dev/null || mktemp -t 'pathtree')
    if [ $? -ne 0 ] || [ -z "$temp_file" ]; then
        echo "Error: Failed to create temporary file." >&2
        return 1
    fi

    # Invoke installed pathtree command directly with user-provided arguments
    pathtree --output "$temp_file" "$@"
    exit_status=$?

    if [ $exit_status -eq 0 ]; then
        if [ -s "$temp_file" ]; then
            # Read the selected path without executing or evaluating its contents
            target_path=$(cat "$temp_file")

            # Verify the selected target is an existing directory
            if [ -d "$target_path" ]; then
                # Change directory
                cd -- "$target_path"
                cd_status=$?
                if [ $cd_status -ne 0 ]; then
                    echo "Error: Could not navigate to $target_path" >&2
                    rm -f "$temp_file"
                    return $cd_status
                fi
            else
                echo "Error: Target path is not a valid directory: $target_path" >&2
                rm -f "$temp_file"
                return 1
            fi
        fi
    else
        # Preserve non-zero status
        rm -f "$temp_file"
        return $exit_status
    fi

    rm -f "$temp_file"
    return 0
}
