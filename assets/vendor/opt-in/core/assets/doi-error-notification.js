/**
 * Double Opt-In — Universal Error Notification
 *
 * Listens for form submission events from any supported form plugin
 * and checks the server-side AJAX endpoint for OptIn creation errors.
 * Displays a toast notification if an error is found.
 *
 * @since 4.2.0
 */
(function () {
	'use strict';

	if ( typeof doiErrorNotification === 'undefined' ) {
		return;
	}

	var config   = doiErrorNotification;
	var checking = false;
	var cooldown = false;

	/**
	 * Check the AJAX endpoint for a stored submission error.
	 */
	function checkForError() {
		if ( checking || cooldown ) {
			return;
		}
		checking = true;

		var xhr = new XMLHttpRequest();
		xhr._doiInternal = true; // Prevent the XHR interceptor from re-triggering scheduleCheck
		xhr.open( 'POST', config.ajaxUrl, true );
		xhr.setRequestHeader( 'Content-Type', 'application/x-www-form-urlencoded' );

		xhr.onreadystatechange = function () {
			if ( xhr.readyState !== 4 ) {
				return;
			}
			checking = false;

			if ( xhr.status !== 200 ) {
				return;
			}

			try {
				var response = JSON.parse( xhr.responseText );
			} catch ( e ) {
				return;
			}

			if ( response.success && response.data && response.data.error ) {
				// Hide form confirmation messages when validation error should be visible
				if ( response.data.error.hide_confirmation ) {
					hideFormConfirmations();
				}

				// Redirect to error page if configured, otherwise show toast
				if ( response.data.redirect_url ) {
					window.location.href = response.data.redirect_url;
					return;
				}

				showNotification( response.data.error.message );

				// Prevent duplicate checks for 5 seconds
				cooldown = true;
				setTimeout( function () {
					cooldown = false;
				}, 5000 );
			}
		};

		xhr.send(
			'action=doi_check_submission_error&nonce=' + encodeURIComponent( config.nonce )
		);
	}

	/**
	 * Schedule an error check with a short delay to ensure
	 * the server-side form processing has completed.
	 */
	function scheduleCheck() {
		setTimeout( checkForError, 800 );
	}

	/**
	 * Hide form plugin confirmation/success messages.
	 *
	 * Called when a validation error should be visible (block/redirect mode)
	 * so the user does not see a contradictory success message.
	 */
	function hideFormConfirmations() {
		// WPForms confirmation containers
		var wpfSelectors = '.wpforms-confirmation-container-full, .wpforms-confirmation-container';
		document.querySelectorAll( wpfSelectors ).forEach( function ( el ) {
			el.style.display = 'none';
		} );

		// Gravity Forms confirmation wrapper
		document.querySelectorAll( '.gform_confirmation_wrapper' ).forEach( function ( el ) {
			el.style.display = 'none';
		} );

		// CF7 success response (only hide the success state, not error state)
		document.querySelectorAll( '.scf7-response-output.scf7-mail-sent-ok' ).forEach( function ( el ) {
			el.style.display = 'none';
		} );

		// Elementor Forms success message
		document.querySelectorAll( '.elementor-message.elementor-message-success' ).forEach( function ( el ) {
			el.style.display = 'none';
		} );
	}

	/**
	 * Show a toast notification with the error message.
	 *
	 * @param {string} message The error message to display.
	 */
	function showNotification( message ) {
		var existing = document.querySelector( '.doi-error-notification' );
		if ( existing ) {
			existing.remove();
		}

		var notification = document.createElement( 'div' );
		notification.className = 'doi-error-notification';
		notification.setAttribute( 'role', 'alert' );

		var content = document.createElement( 'div' );
		content.className = 'doi-error-notification__content';

		var icon = document.createElement( 'span' );
		icon.className = 'doi-error-notification__icon';
		icon.innerHTML = '&#9888;';

		var text = document.createElement( 'p' );
		text.className = 'doi-error-notification__message';
		text.textContent = message;

		var closeBtn = document.createElement( 'button' );
		closeBtn.className = 'doi-error-notification__close';
		closeBtn.setAttribute( 'type', 'button' );
		closeBtn.innerHTML = '&times;';
		closeBtn.addEventListener( 'click', function () {
			dismiss( notification );
		} );

		content.appendChild( icon );
		content.appendChild( text );
		content.appendChild( closeBtn );
		notification.appendChild( content );
		document.body.appendChild( notification );

		// Trigger enter animation
		requestAnimationFrame( function () {
			notification.classList.add( 'doi-error-notification--visible' );
		} );

		// Auto-dismiss after 10 seconds
		setTimeout( function () {
			dismiss( notification );
		}, 10000 );
	}

	/**
	 * Dismiss a notification with exit animation.
	 *
	 * @param {HTMLElement} el The notification element.
	 */
	function dismiss( el ) {
		if ( ! el || ! el.parentNode ) {
			return;
		}
		el.classList.remove( 'doi-error-notification--visible' );
		el.classList.add( 'doi-error-notification--exit' );
		setTimeout( function () {
			if ( el.parentNode ) {
				el.parentNode.removeChild( el );
			}
		}, 300 );
	}

	// -------------------------------------------------------------------------
	// Form plugin event listeners
	// -------------------------------------------------------------------------

	// Contact Form 7 (native DOM events)
	document.addEventListener( 'scf7mailsent', scheduleCheck );
	document.addEventListener( 'scf7invalid', scheduleCheck );
	document.addEventListener( 'scf7spam', scheduleCheck );
	document.addEventListener( 'scf7mailfailed', scheduleCheck );

	// WPForms + Gravity Forms (jQuery events — not caught by native addEventListener)
	if ( typeof jQuery !== 'undefined' ) {
		jQuery( document ).on( 'wpformsAjaxSubmitSuccess', scheduleCheck );
		jQuery( document ).on( 'wpformsAjaxSubmitError', scheduleCheck );
		jQuery( document ).on( 'gform_confirmation_loaded', scheduleCheck );
	}

	// -------------------------------------------------------------------------
	// Universal: catch ANY form submission on the page (capture phase)
	// This is the most reliable way to detect form submissions regardless
	// of which form plugin is used. It covers AJAX, standard, and custom flows.
	// -------------------------------------------------------------------------
	document.addEventListener( 'submit', function () {
		// Use a longer delay for standard (non-AJAX) submissions
		// because the server needs time to process the request.
		setTimeout( checkForError, 1500 );
	}, true );

	// -------------------------------------------------------------------------
	// Generic AJAX interception
	// Catches all AJAX calls to detect form submissions from plugins
	// that don't fire specific events (e.g., Sca, Elementor).
	// -------------------------------------------------------------------------

	// Intercept fetch()
	if ( typeof window.fetch === 'function' ) {
		var originalFetch = window.fetch;
		window.fetch = function () {
			// Capture URL before the async call — `arguments` inside .then()
			// refers to the callback's own arguments, not the fetch arguments.
			var fetchUrl = ( typeof arguments[0] === 'string' )
				? arguments[0]
				: ( arguments[0] && arguments[0].url ) || '';

			return originalFetch.apply( this, arguments ).then( function ( response ) {
				if ( fetchUrl && fetchUrl.indexOf( 'admin-ajax.php' ) !== -1 ) {
					scheduleCheck();
				}
				return response;
			} );
		};
	}

	// Intercept XMLHttpRequest for jQuery.ajax based form plugins
	var origOpen = XMLHttpRequest.prototype.open;
	XMLHttpRequest.prototype.open = function ( method, url ) {
		// Skip our own internal error-check requests to prevent infinite polling loops
		if ( typeof url === 'string' && url.indexOf( 'admin-ajax.php' ) !== -1 && ! this._doiInternal ) {
			this.addEventListener( 'load', scheduleCheck );
		}
		return origOpen.apply( this, arguments );
	};

})();
