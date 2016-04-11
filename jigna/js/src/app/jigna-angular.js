// An AngularJS app running the jigna app

// Namespace for the angular app of jigna
jigna.angular = {};

jigna.angular.app = angular.module('jigna', []);

// Add initialization function on module run time
jigna.angular.app.run(['$rootScope', '$compile', function($rootScope, $compile){

    // add the 'jigna' namespace to the $rootScope. This is done so that
    // any special jigna methods are easily available in directives like
    // ng-click, ng-mouseover etc.
    $rootScope.jigna = jigna;

    jigna.ready.done(function(){
        var models = jigna.models;

        jigna.client.print_JS_message('adding models');
        for (var model_name in models) {
            $rootScope[model_name] = models[model_name];
        }
    });

    // Start the $digest cycle on rootScope whenever anything in the
    // model object is changed.
    //
    // Since the $digest cycle essentially involves dirty checking of
    // all the watchers, this operation means that it will trigger off
    // new GET requests for each model attribute that is being used in
    // the registered watchers.
    jigna.add_listener('jigna', 'object_changed', function() {
        if ($rootScope.$$phase === null){
            $rootScope.$digest();
        }
    });

}]);
