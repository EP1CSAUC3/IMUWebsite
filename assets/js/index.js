$(document).on('click','.js-videoPoster',function(e) {
  
  e.preventDefault();
  var poster = $(this);
  
  var wrapper = poster.closest('.js-videoWrapper');
  videoPlay(wrapper);
});


function videoPlay(wrapper) {
  var iframe = wrapper.find('.js-videoIframe')
  var src = iframe.data('src');
 
  wrapper.addClass('videoWrapperActive');
  
  iframe.attr('src', src);
}