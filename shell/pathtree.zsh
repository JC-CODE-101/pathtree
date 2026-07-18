# PathTree Zsh Integration
# To use, add 'source /path/to/pathtree.zsh' to your ~/.zshrc

pb() {
    # Keep variables local to the function
    local temp_file
    local exit_status
    local target_path
    local cd_status

    temp_file=$(mktemp 2>/dev/null || mktemp -t 'pathtree')
    if [ $? -ne 0 ] || [ -z "$temp_file" ]; then
        echo "Error: Failed to create temporary file." >&2
        return 1
    fi

    {
        # Run pathtree within the protected try block
        pathtree --output "$temp_file" "$@"
        exit_status=$?

        if [ $exit_status -eq 0 ]; then
            if [ -s "$temp_file" ]; then
                # Read selected path without eval/source
                target_path=$(cat "$temp_file")

                # Verify the selected target is an existing directory
                if [ -d "$target_path" ]; then
                    # Change directory using Zsh builtin cd
                    builtin cd -- "$target_path"
                    cd_status=$?
                    if [ $cd_status -ne 0 ]; then
                        echo "Error: Could not navigate to $target_path" >&2
                        return $cd_status
                    fi
                else
                    echo "Error: Target path is not a valid directory: $target_path" >&2
                    return 1
                fi
            fi
        else
            return $exit_status
        fi
    } always {
        # The always block is guaranteed to execute, even on interruptions or cancellations
        rm -f "$temp_file"
    }
}
