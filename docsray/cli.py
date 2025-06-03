def process_pdf_with_timeout(pdf_path: str, analyze_visuals: bool, timeout: int):
    """Process PDF with optional timeout handling"""
    def _process():
        from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder
        
        # Extract
        print("📖 Extracting content...")
        extracted = pdf_extractor.extract_content(
            pdf_path,
            analyze_visuals=analyze_visuals
        )

        # Chunk
        print("✂️  Creating chunks...")
        chunks = chunker.process_extracted_file(extracted)
        
        # Build index
        print("🔍 Building search index...")
        chunk_index = build_index.build_chunk_index(chunks)
        
        # Build section representations
        print("📊 Building section representations...")
        sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)
        
        return sections, chunks
    
    # Check if timeout is enabled
    if timeout > 0:
        # Run with timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            print(f"⏰ Processing timeout: {timeout} seconds ({timeout//60}m {timeout%60}s)")
            future = executor.submit(_process)
            
            try:
                sections, chunks = future.result(timeout=timeout)
                return sections, chunks
            except concurrent.futures.TimeoutError:
                future.cancel()
                print(f"\n⏰ Processing timeout exceeded!")
                print(f"❌ Document processing took longer than {timeout} seconds")
                print(f"💡 Try with a smaller document or use --no-visuals flag")
                raise ProcessingTimeoutError(f"Processing timeout after {timeout} seconds")
    else:
        # Run without timeout
        print("⏰ No timeout limit set")
        return _process()


# Also update the process_document_with_timeout in web_demo.py
def process_document_with_timeout(file_path: str, session_dir: Path, analyze_visuals: bool = True, progress_callback=None) -> Tuple[list, list, str]:
    """Process a document file with optional timeout handling"""
    def _do_process():
        start_time = time.time()
        file_name = Path(file_path).name
        
        try:
            # Extract content with visual analysis option
            if progress_callback is not None:
                status_msg = f"📖 Extracting content from {file_name}..."
                if analyze_visuals:
                    status_msg += " (with visual analysis)"
                progress_callback(0.2, status_msg)
            
            extracted = pdf_extractor.extract_content(
                file_path,
                analyze_visuals=analyze_visuals,
                page_limit=PAGE_LIMIT if PAGE_LIMIT > 0 else None
            )
            
            # Create chunks
            if progress_callback is not None:
                progress_callback(0.4, "✂️ Creating text chunks...")
            
            chunks = chunker.process_extracted_file(extracted)
            
            # Build search index
            if progress_callback is not None:
                progress_callback(0.6, "🔍 Building search index...")
            
            chunk_index = build_index.build_chunk_index(chunks)
            
            # Build section representations
            if progress_callback is not None:
                progress_callback(0.8, "📊 Building section representations...")
            
            sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)
            
            # Save to session cache
            if progress_callback is not None:
                progress_callback(0.9, "💾 Saving to cache...")
            
            cache_data = {
                "sections": sections,
                "chunk_index": chunk_index,
                "filename": file_name,
                "metadata": extracted.get("metadata", {})
            }
            
            # Save with pickle for better performance
            cache_file = session_dir / f"{Path(file_path).stem}_cache.pkl"
            with open(cache_file, "wb") as f:
                pickle.dump(cache_data, f)
            
            # Calculate processing time
            elapsed_time = time.time() - start_time
            
            # Create status message
            was_converted = extracted.get("metadata", {}).get("was_converted", False)
            original_format = extracted.get("metadata", {}).get("original_format", "")
            
            msg = f"✅ Successfully processed: {file_name}\n"
            if was_converted:
                msg += f"🔄 Converted from {original_format.upper()} to PDF\n"
            msg += f"📑 Sections: {len(sections)}\n"
            msg += f"🔍 Chunks: {len(chunks)}\n"
            msg += f"⏱️ Processing time: {elapsed_time:.1f} seconds"
            
            if progress_callback is not None:
                progress_callback(1.0, "✅ Processing complete!")
            
            return sections, chunk_index, msg
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Error processing {file_name} after {elapsed_time:.1f}s: {str(e)}")
            raise
    
    # Check if timeout is enabled
    if PDF_PROCESS_TIMEOUT > 0:
        start_time = time.time()
        file_name = Path(file_path).name
        
        # Progress: Starting
        if progress_callback is not None:
            progress_callback(0.1, f"📄 Starting to process: {file_name}")
        
        # Create a thread pool for timeout handling
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            # Submit the processing task
            future = executor.submit(_do_process)
            
            try:
                # Wait for completion with timeout
                return future.result(timeout=PDF_PROCESS_TIMEOUT)
            except concurrent.futures.TimeoutError:
                # Cancel the future if possible
                future.cancel()
                
                elapsed_time = time.time() - start_time
                error_msg = f"⏰ Processing timeout: {file_name}\n"
                error_msg += f"⚠️ Document processing exceeded {PDF_PROCESS_TIMEOUT//60} minutes limit\n"
                error_msg += f"📊 Elapsed time: {elapsed_time:.1f} seconds\n"
                error_msg += f"💡 Try with a smaller document or disable visual analysis"
                
                logger.error(f"PDF processing timeout for {file_name} after {elapsed_time:.1f}s")
                
                # Force cleanup
                gc.collect()
                
                raise ProcessingTimeoutError(error_msg)
    else:
        # Run without timeout
        if progress_callback is not None:
            progress_callback(0.1, f"📄 Starting to process: {Path(file_path).name} (no timeout)")
        return _do_process()


# Update get_supported_formats to conditionally show timeout info
def get_supported_formats() -> str:
    """Get list of supported file formats"""
    converter = FileConverter()
    formats = converter.get_supported_formats()
    
    # Group by category
    categories = {
        "Office Documents": ['.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.odt', '.ods', '.odp'],
        "Text Files": ['.txt', '.md', '.rst', '.rtf'],
        "Web Files": ['.html', '.htm', '.xml'],
        "Images": ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'],
        "E-books": ['.epub', '.mobi'],
        "PDF": ['.pdf']
    }
    
    info = "📄 **Supported File Formats:**\n\n"
    for category, extensions in categories.items():
        supported_exts = [ext for ext in extensions if ext in formats or ext == '.pdf']
        if supported_exts:
            info += f"**{category}:** {', '.join(supported_exts)}\n"

    # Only show timeout info if timeout is enabled
    if PDF_PROCESS_TIMEOUT > 0:
        info += f"\n⏰ **Processing Timeout:** {PDF_PROCESS_TIMEOUT//60} minutes per document\n"
        info += "💡 **Tip:** Disable visual analysis for faster processing of large documents"
    else:
        info += "\n⏰ **Processing Timeout:** Disabled (no time limit)\n"
        info += "💡 **Note:** Large documents may take significant time to process"
    
    return info