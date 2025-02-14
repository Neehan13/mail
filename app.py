@app.route('/send', methods=['GET', 'POST'])
@login_required
def send_email():
    if request.method == 'POST':
        try:
            app.logger.info("Starting email sending process")
            # Get sender credentials
            sender_email = request.form.get('sender_email')
            sender_password = request.form.get('sender_password')
            
            if not sender_email or not sender_password:
                flash('Sender email and password are required', 'error')
                return render_template('send_email.html')

            # Get recipients based on input method
            recipients_method = request.form.get('recipients_method', 'manual')
            recipients_list = []
            
            if recipients_method == 'manual':
                recipients_input = request.form.get('recipients', '').strip()
                if not recipients_input:
                    flash('Recipients are required', 'error')
                    return render_template('send_email.html')
                recipients_list = parse_recipients(recipients_input)
            else:
                if 'recipients_file' not in request.files:
                    flash('Recipients file is required', 'error')
                    return render_template('send_email.html')
                    
                file = request.files['recipients_file']
                if file.filename == '':
                    flash('No file selected', 'error')
                    return render_template('send_email.html')
                    
                if not file.filename.endswith('.txt'):
                    flash('Only .txt files are allowed', 'error')
                    return render_template('send_email.html')
                    
                # Save and process recipients file
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                recipients_list = parse_recipients(None, filepath)
                os.remove(filepath)  # Clean up after processing
            
            if not recipients_list:
                flash('No valid recipients found', 'error')
                return render_template('send_email.html')

            app.logger.info(f"Found {len(recipients_list)} recipients")

            # Get other email details
            subject = request.form.get('subject', '').strip()
            body = request.form.get('body', '').strip()
            
            if not subject or not body:
                flash('Subject and body are required', 'error')
                return render_template('send_email.html')

            # Handle attachments
            attachments = []
            if 'attachments' in request.files:
                files = request.files.getlist('attachments')
                for file in files:
                    if file.filename:
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        attachments.append(filepath)
                        app.logger.info(f"Saved attachment: {filepath}")

            try:
                app.logger.info("Initializing email sender")
                
                # Determine tracking server URL based on request
                tracking_server = f"{request.scheme}://{request.host}"
                app.logger.info(f"Using tracking server: {tracking_server}")
                
                # Initialize email sender with tracking server
                sender = EmailSender(
                    sender_email, 
                    sender_password,
                    tracking_server=tracking_server
                )
                
                # Generate campaign ID (today's date)
                campaign_id = get_campaign_id()
                
                # Prepare email details for each recipient
                email_list = [
                    (recipient, subject, body, campaign_id, attachments)
                    for recipient in recipients_list
                ]
                
                app.logger.info(f"Starting to send {len(email_list)} emails")
                # Send emails
                results = sender.send_emails_threaded(email_list)
                
                # Clean up attachments
                for filepath in attachments:
                    try:
                        os.remove(filepath)
                        app.logger.info(f"Cleaned up attachment: {filepath}")
                    except Exception as e:
                        app.logger.error(f"Error removing attachment {filepath}: {str(e)}")

                # Calculate success/failure
                successes = sum(1 for success, _ in results if success)
                failures = len(results) - successes
                
                app.logger.info(f'Email campaign completed - Success: {successes}, Failed: {failures}')
                
                if failures == 0:
                    flash(f'Successfully sent {successes} emails', 'success')
                else:
                    error_messages = [err for success, err in results if not success and err]
                    unique_errors = list(set(error_messages))  # Remove duplicate error messages
                    flash(f'Sent {successes} emails, {failures} failed. Errors: {"; ".join(unique_errors)}', 'warning')
                
                return redirect(url_for('dashboard.index'))
                
            except Exception as e:
                error_msg = f'Error sending emails: {str(e)}'
                app.logger.error(error_msg)
                flash(error_msg, 'error')
                return render_template('send_email.html')
                
        except Exception as e:
            error_msg = f'Error processing request: {str(e)}'
            app.logger.error(error_msg)
            flash(error_msg, 'error')
            return render_template('send_email.html')

    return render_template('send_email.html') 